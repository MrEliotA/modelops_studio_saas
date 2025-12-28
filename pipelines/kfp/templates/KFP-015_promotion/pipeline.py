"""KFP-015 Promotion Gate

    Pipeline sources are intentionally small. The runtime artifact is IR YAML.
    """

    from kfp import dsl, components

    dq_check_op = components.load_component_from_file("pipelines/kfp/components/quality/dq_check/component.yaml")
    train_op = components.load_component_from_file("pipelines/kfp/components/train/train_tabular/component.yaml")
    eval_op = components.load_component_from_file("pipelines/kfp/components/eval/evaluate_metrics/component.yaml")
    register_op = components.load_component_from_file("pipelines/kfp/components/registry/register_model/component.yaml")
    deploy_staging_op = components.load_component_from_file("pipelines/kfp/components/deploy/deploy_staging/component.yaml")
    smoke_test_op = components.load_component_from_file("pipelines/kfp/components/deploy/smoke_test/component.yaml")
    approval_op = components.load_component_from_file("pipelines/kfp/components/deploy/manual_approval_gate/component.yaml")
    promote_op = components.load_component_from_file("pipelines/kfp/components/deploy/promote_prod/component.yaml")
    opencost_pull_op = components.load_component_from_file("pipelines/kfp/components/finops/opencost_pull/component.yaml")
    invoice_preview_op = components.load_component_from_file("pipelines/kfp/components/finops/invoice_preview/component.yaml")

    @dsl.pipeline(name="kfp-015-promotion")
def promotion_pipeline(
    model_version_id: str,
    approval_ticket_id: str,
    approval_timeout_seconds: int = 3600,
    traffic_shift: str = "replace",
):
    staging = deploy_staging_op({"Model version id": model_version_id})
    _ = smoke_test_op({"Endpoint url": staging.outputs["Endpoint url"]})
    gate = approval_op({"Approval ticket id": approval_ticket_id, "Timeout seconds": approval_timeout_seconds})
    with dsl.Condition(gate.outputs["Approved"] == "true"):
        _ = promote_op({"Model version id": model_version_id, "Traffic shift": traffic_shift})

