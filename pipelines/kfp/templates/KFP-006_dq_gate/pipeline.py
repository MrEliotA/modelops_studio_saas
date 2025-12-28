"""KFP-006 Data Quality Gate

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

    @dsl.pipeline(name="kfp-006-dq-gated-train")
def dq_gated_train_pipeline(
    dataset_uri: str,
    dq_ruleset: str = "default",
    fail_mode: str = "stop",
    label_col: str = "label",
    algorithm: str = "xgboost",
):
    dq = dq_check_op(
        **{
            "Dataset URI": dataset_uri,
            "Ruleset": dq_ruleset,
            "Fail mode": fail_mode,
        }
    )
    with dsl.Condition(dq.outputs["Proceed"] == "true"):
        _ = train_op(
            **{
                "Dataset URI": dataset_uri,
                "Label column": label_col,
                "Algorithm": algorithm,
            }
        )

