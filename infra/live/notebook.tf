module "notebook" {
  count  = var.github_repo == null ? 0 : 1
  source = "../modules/notebook"

  subnet_id = data.aws_subnet.host.id
  repo_url  = "https://github.com/${var.github_repo}"
  env = {
    AWS_REGION          = "us-east-1"
    MLFLOW_TRACKING_URI = "http://${module.host["platform"].private_ip}:5000"
    REDSHIFT_CLUSTER_ID = module.redshift.cluster_id
    REDSHIFT_DATABASE   = module.redshift.database
    REDSHIFT_DB_USER    = module.redshift.admin_user
  }
}

resource "aws_vpc_security_group_ingress_rule" "notebook_mlflow" {
  count = length(module.notebook)

  security_group_id            = aws_security_group.service["platform"].id
  referenced_security_group_id = module.notebook[count.index].security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5000
  to_port                      = 5000
}

output "notebook_name" {
  value = one(module.notebook[*].name)
}
