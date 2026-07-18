data "aws_region" "current" {}

data "external" "latest_manual_snapshot" {
  count = var.restore_latest_snapshot && var.snapshot_identifier == null ? 1 : 0

  program = [
    "bash",
    "-ce",
    <<-EOT
      ID=$(aws rds describe-db-snapshots \
        --region "${data.aws_region.current.region}" \
        --db-instance-identifier "${var.identifier}" \
        --snapshot-type manual \
        --query 'sort_by(DBSnapshots,&SnapshotCreateTime)[-1].DBSnapshotIdentifier' \
        --output text 2>/dev/null || true)
      case "$ID" in
        ""|None|null) echo '{"id":""}' ;;
        *) printf '{"id":"%s"}\n' "$ID" ;;
      esac
    EOT
  ]
}

locals {
  looked_up_snapshot = try(data.external.latest_manual_snapshot[0].result.id, "")
  snapshot_identifier = (
    var.snapshot_identifier != null
    ? var.snapshot_identifier
    : (local.looked_up_snapshot != "" ? local.looked_up_snapshot : null)
  )
  restoring = local.snapshot_identifier != null
}

resource "random_password" "master" {
  length  = 32
  special = false
}

resource "random_id" "final_snapshot" {
  count = var.skip_final_snapshot ? 0 : 1

  byte_length = 4
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.identifier}-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.identifier}-postgres"
  description = "Postgres access for ${var.identifier}"
  vpc_id      = var.vpc_id
  tags        = var.tags

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "cidr_ingress" {
  for_each = toset(var.allowed_cidr_blocks)

  type              = "ingress"
  from_port         = var.database_port
  to_port           = var.database_port
  protocol          = "tcp"
  cidr_blocks       = [each.value]
  security_group_id = aws_security_group.this.id
  description       = "Postgres from ${each.value}"
}

resource "aws_security_group_rule" "sg_ingress" {
  for_each = toset(var.allowed_security_group_ids)

  type                     = "ingress"
  from_port                = var.database_port
  to_port                  = var.database_port
  protocol                 = "tcp"
  source_security_group_id = each.value
  security_group_id        = aws_security_group.this.id
  description              = "Postgres from SG ${each.value}"
}

resource "aws_secretsmanager_secret" "master" {
  name                    = "${var.identifier}/master"
  recovery_window_in_days = 0
  tags                    = var.tags
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.master.result
    engine   = "postgres"
    host     = aws_db_instance.this.address
    port     = aws_db_instance.this.port
    dbname   = var.db_name
  })
}

resource "aws_db_instance" "this" {
  identifier = var.identifier

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage > 0 ? var.max_allocated_storage : null
  storage_type          = "gp3"
  storage_encrypted     = true

  username = local.restoring ? null : var.master_username
  password = random_password.master.result
  port     = var.database_port

  snapshot_identifier = local.snapshot_identifier

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  backup_retention_period   = var.backup_retention_period
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.identifier}-final-${random_id.final_snapshot[0].hex}"

  db_name = local.restoring ? null : var.db_name

  allow_major_version_upgrade = true

  apply_immediately     = true
  copy_tags_to_snapshot = true

  tags = var.tags

  lifecycle {
    ignore_changes = [snapshot_identifier]
  }
}
