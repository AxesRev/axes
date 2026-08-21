terraform {
  required_version = ">= 1.15.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.61"
    }
    auth0 = {
      source  = "auth0/auth0"
      version = ">= 1.55.0"
    }
  }
}
