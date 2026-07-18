locals {
  password = var.password != null ? var.password : random_password.this[0].result
}

resource "random_password" "this" {
  count = var.password == null ? 1 : 0

  length  = 24
  special = false
}

resource "aws_ebs_volume" "this" {
  availability_zone = var.availability_zone
  size              = var.size_gb
  type              = "gp3"
  encrypted         = true

  tags = merge(var.tags, {
    Name = var.name
  })
}
