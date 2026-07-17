locals {
  app_username = var.app_username != null ? var.app_username : "${var.name}_app"
  app_password = var.create_app_user ? (
    var.app_password != null ? var.app_password : random_password.app[0].result
  ) : null
}

resource "random_password" "app" {
  count = var.create_app_user && var.app_password == null ? 1 : 0

  length  = 32
  special = false
}

resource "postgresql_database" "this" {
  name = var.name
  owner = var.owner
}

resource "postgresql_role" "app" {
  count = var.create_app_user ? 1 : 0

  name     = local.app_username
  login    = true
  password = local.app_password
}

resource "postgresql_grant" "app_database" {
  count = var.create_app_user ? 1 : 0

  database    = postgresql_database.this.name
  role        = postgresql_role.app[0].name
  object_type = "database"
  privileges  = ["CONNECT", "TEMPORARY"]
}

resource "postgresql_grant" "app_schema" {
  count = var.create_app_user ? 1 : 0

  database    = postgresql_database.this.name
  role        = postgresql_role.app[0].name
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE", "CREATE"]
}

resource "postgresql_extension" "this" {
  for_each = toset(var.extensions)

  name     = each.value
  database = postgresql_database.this.name
}
