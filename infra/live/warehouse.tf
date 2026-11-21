module "redshift" {
  source            = "../modules/redshift"
  subnet_ids        = sort(data.aws_subnets.default.ids)
  availability_zone = var.availability_zone
}

output "redshift_cluster_id" {
  value = module.redshift.cluster_id
}

output "redshift_database" {
  value = module.redshift.database
}
