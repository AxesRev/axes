terraform {
  required_version = ">= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.55"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}
