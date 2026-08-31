variable "namespace" {
  description = "Namespace that already holds the Postgres, GitHub, and Salesforce secrets (langraph-server)."
  type        = string
}

variable "image" {
  description = "graph-service container image (ECR)."
  type        = string
}

variable "bolt_uri" {
  description = "Neo4j bolt URI inside the cluster."
  type        = string
}

variable "neo4j_uid" {
  description = "Neo4j StatefulSet UID. The one-shot Job is named from this so it runs only when Neo4j is created."
  type        = string
}

variable "postgres_secret_name" {
  description = "Existing secret with POSTGRES_* keys."
  type        = string
}

variable "github_secret_name" {
  description = "Existing secret with GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY."
  type        = string
}

variable "salesforce_secret_name" {
  description = "Existing secret with SALESFORCE_CLIENT_ID, SALESFORCE_PRIVATE_KEY, SALESFORCE_LOGIN_URL."
  type        = string
}

variable "neo4j_password" {
  description = "Neo4j password from the neo4j stack. Copied into this namespace because secret_key_ref cannot cross namespaces."
  type        = string
  sensitive   = true
}
