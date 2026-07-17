output "instance_id" {
  value = aws_db_instance.this.id
}

output "address" {
  value = aws_db_instance.this.address
}

output "endpoint" {
  value = aws_db_instance.this.endpoint
}

output "port" {
  value = aws_db_instance.this.port
}

output "master_username" {
  value = var.master_username
}

output "master_password" {
  value     = random_password.master.result
  sensitive = true
}

output "master_secret_arn" {
  value = aws_secretsmanager_secret.master.arn
}

output "security_group_id" {
  value = aws_security_group.this.id
}

output "connection_host" {
  description = "Hostname for app connection strings (no port)."
  value       = aws_db_instance.this.address
}
