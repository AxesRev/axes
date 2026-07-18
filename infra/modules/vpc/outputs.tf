output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnets" {
  value = module.vpc.private_subnets
}

output "public_subnets" {
  value = module.vpc.public_subnets
}

output "azs" {
  value = module.vpc.azs
}

output "db_clients_security_group_id" {
  description = "Stable SG to attach to workloads that may connect to RDS."
  value       = aws_security_group.db_clients.id
}
