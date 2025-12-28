"""KFP-020 OpenCost Chargeback

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

    @dsl.pipeline(name="kfp-020-opencost-chargeback")
def chargeback_pipeline(
    opencost_base_url: str = "http://opencost.opencost:9003",
    window: str = "7d",
    aggregate: str = "namespace",
    resolution: str = "1m",
    include_idle: bool = False,
    share_idle: bool = True,
    rate_card_id: str = "default",
):
    alloc = opencost_pull_op(
        **{
            "Base URL": opencost_base_url,
            "Window": window,
            "Aggregate": aggregate,
            "Resolution": resolution,
            "Include idle": include_idle,
            "Share idle": share_idle,
        }
    )
    _ = invoice_preview_op({"Allocation raw": alloc.outputs["Allocation raw"], "Rate card id": rate_card_id})

