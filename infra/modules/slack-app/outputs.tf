output "namespace" {
  value = kubernetes_namespace_v1.this.metadata[0].name
}

output "invoke_url" {
  description = "Public HTTPS URL for Slack request URLs."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "internal_url" {
  description = "Internal NLB base URL for in-VPC callers (billing Lambda)."
  value       = "http://${aws_lb.this.dns_name}"
}
