output "volume_id" {
  value = aws_ebs_volume.this.id
}

output "availability_zone" {
  value = aws_ebs_volume.this.availability_zone
}

output "size_gb" {
  value = aws_ebs_volume.this.size
}

output "password" {
  value     = local.password
  sensitive = true
}
