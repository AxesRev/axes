output "job_name" {
  value = kubernetes_job_v1.this.metadata[0].name
}

output "cron_job_name" {
  description = "Suspended CronJob used to rerun fetch. kubectl create job --from=cronjob/fetch-graph"
  value       = kubernetes_cron_job_v1.manual.metadata[0].name
}
