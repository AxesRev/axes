terraform {
  required_version = ">= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.61"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.2"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}
