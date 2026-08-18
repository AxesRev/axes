output "invoke_url" {
  description = "Public HTTPS URL for Slack request URLs."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "internal_url" {
  description = "Internal NLB base URL for in-VPC callers."
  value       = "http://${aws_lb.this.dns_name}"
}

output "node_port" {
  value = var.node_port
}
