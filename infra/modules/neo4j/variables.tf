variable "namespace" {
  description = "Kubernetes namespace for Neo4j."
  type        = string
  default     = "neo4j"
}

variable "image" {
  description = "Neo4j container image."
  type        = string
  default     = "neo4j:5.26.28-community"
}

variable "storage_size" {
  description = "Persistent volume size for Neo4j data."
  type        = string
  default     = "20Gi"
}

variable "password" {
  description = "Neo4j password. If null, a random password is generated."
  type        = string
  default     = null
  sensitive   = true
}

variable "create_storage_class" {
  description = "Create a gp3 StorageClass (EBS CSI). Set false if one already exists."
  type        = bool
  default     = true
}

variable "storage_class_name" {
  description = "StorageClass name for the Neo4j PVC."
  type        = string
  default     = "gp3"
}
