variable "name" {
  description = "Name tag for the Neo4j data volume."
  type        = string
}

variable "availability_zone" {
  description = "AZ for the EBS volume. Neo4j pods must schedule in this AZ."
  type        = string
}

variable "size_gb" {
  description = "EBS volume size in GiB."
  type        = number
  default     = 20
}

variable "password" {
  description = "Neo4j password. If null, a random password is generated and kept in this stack."
  type        = string
  default     = null
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to the EBS volume."
  type        = map(string)
  default     = {}
}
