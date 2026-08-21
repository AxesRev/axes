output "values" {
  description = "Decoded JSON from the existing SSM parameter."
  value       = local.values
  sensitive   = true
}
