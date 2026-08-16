output "state_bucket_name" {
  value = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  value = aws_s3_bucket.state.arn
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "github_actions_deploy_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "github_actions_deploy_role_name" {
  value = aws_iam_role.github_actions.name
}

output "account_id" {
  value = data.aws_caller_identity.current.account_id
}
