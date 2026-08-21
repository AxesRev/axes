terraform {
  required_version = ">= 1.15.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.55"
    }
    auth0 = {
      source  = "auth0/auth0"
      version = ">= 1.55.0"
    }
  }
}
