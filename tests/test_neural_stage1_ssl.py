import os

import pytest

from Sys.RootCauseAnalyze.stage1.neural_graph import (
    EventVocabulary,
    GraphBuildConfig,
    PathConditionedGraphBuilder,
    RawCase,
)
from Sys.RootCauseAnalyze.stage1.neural_ssl_pipeline import (
    MODEL_NAME,
    MODEL_VERSION,
    _without_labels,
    build_parser,
    result_record,
)


def _case(dirpath="ssl-case", *, label="D1"):
    return RawCase(
        dirpath=dirpath,
        nodes=[
            {
                "mgmt_ip": "D1",
                "role": "LEAF",
                "linked_from": ["host-a"],
                "linked_to": ["D2"],
                "cross": 2,
                "alarms": [
                    {
                        "alarm_name": "linkDown_active",
                        "alarm_time": 1_000,
                        "alarm_level": 3,
                        "alarm_weight": 70,
                    }
                ],
                "logs": [],
            },
            {
                "mgmt_ip": "D2",
                "role": "SPINE",
                "linked_from": ["D1"],
                "linked_to": ["host-b"],
                "cross": 1,
                "alarms": [],
                "logs": [
                    {
                        "name": "bgpBackwardTransition_active",
                        "alarm_time": 1_500,
                        "alarm_level": 2,
                    }
                ],
            },
        ],
        info={
            "alarm_time": 2_000,
            "alarm_name": "pingmesh",
            "source_ip": ["host-a"],
            "sink_ip": ["host-b"],
        },
        gt_ip=label,
    )


def _graphs():
    labeled_case = _case()
    label_free_case = _case(label=None)
    vocabulary = EventVocabulary.fit([label_free_case], max_size=16)
    builder = PathConditionedGraphBuilder(
        vocabulary,
        config=GraphBuildConfig(max_events_per_device=4, max_events_total=8),
    )
    return (
        vocabulary,
        builder.build(label_free_case, include_labels=False),
        builder.build(labeled_case, include_labels=True),
    )


def test_ssl_network_is_separate_from_the_original_pc_stgr():
    pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.neural_model import (
        NeuralModelConfig,
        PathConditionedGraphRanker,
    )
    from Sys.RootCauseAnalyze.stage1.neural_ssl_model import (
        SelfSupervisedPathConditionedGraphRanker,
    )

    config = NeuralModelConfig(hidden_dim=8, heads=2, layers=1)
    original = PathConditionedGraphRanker(4, config)
    ssl_model = SelfSupervisedPathConditionedGraphRanker(4, config)

    assert not hasattr(original, "token_reconstruction_head")
    assert hasattr(ssl_model, "token_reconstruction_head")
    assert type(original) is PathConditionedGraphRanker
    assert type(ssl_model) is SelfSupervisedPathConditionedGraphRanker


def test_ssl_losses_are_label_free_and_differentiable():
    torch = pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.neural_model import NeuralModelConfig, graph_to_tensors
    from Sys.RootCauseAnalyze.stage1.neural_ssl_model import (
        PretrainingConfig,
        SelfSupervisedPathConditionedGraphRanker,
        corrupt_graph_batch,
        self_supervised_losses,
    )

    vocabulary, label_free_graph, _labeled_graph = _graphs()
    batch = graph_to_tensors(label_free_graph, torch.device("cpu"))
    config = PretrainingConfig(
        epochs=1,
        gradient_accumulation=1,
        token_mask_rate=1.0,
        feature_mask_rate=1.0,
        edge_drop_rate=0.5,
    )
    corrupted, targets = corrupt_graph_batch(batch, config, seed=7)
    model = SelfSupervisedPathConditionedGraphRanker(
        len(vocabulary.itos),
        NeuralModelConfig(hidden_dim=8, heads=2, layers=1, dropout=0.0),
    )
    losses = self_supervised_losses(model, corrupted, targets, config)
    losses["loss"].backward()

    assert int(batch["root_position"].item()) == -1
    assert targets["token_indices"].numel() == 2
    assert torch.all(corrupted["token_ids"][targets["token_indices"]] == 1)
    assert targets["feature_mask"].any()
    assert corrupted["edge_sources"].numel() < batch["edge_sources"].numel()
    assert targets["edge_pairs"].numel() > 0
    assert torch.isfinite(losses["loss"])
    assert model.input_projection[0].weight.grad is not None


def test_ssl_pretraining_refuses_attached_root_labels():
    torch = pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.neural_model import NeuralModelConfig
    from Sys.RootCauseAnalyze.stage1.neural_ssl_model import PretrainingConfig, pretrain_model

    vocabulary, _label_free_graph, labeled_graph = _graphs()
    with pytest.raises(ValueError, match="must not contain root labels"):
        pretrain_model(
            [labeled_graph],
            vocabulary_size=len(vocabulary.itos),
            model_config=NeuralModelConfig(hidden_dim=8, heads=2, layers=1),
            pretraining_config=PretrainingConfig(epochs=1),
            device=torch.device("cpu"),
        )


def test_ssl_pretrain_finetune_checkpoint_and_prediction_round_trip(tmp_path):
    torch = pytest.importorskip("torch")
    from Sys.RootCauseAnalyze.stage1.neural_model import NeuralModelConfig, TrainingConfig
    from Sys.RootCauseAnalyze.stage1.neural_ssl_model import (
        CHECKPOINT_FORMAT,
        PretrainingConfig,
        SelfSupervisedPathConditionedGraphRanker,
        finetune_model,
        load_checkpoint,
        predict_graph,
        pretrain_model,
        save_checkpoint,
    )

    vocabulary, label_free_graph, labeled_graph = _graphs()
    model_config = NeuralModelConfig(hidden_dim=8, heads=2, layers=1, dropout=0.0)
    pretraining_config = PretrainingConfig(
        epochs=1,
        gradient_accumulation=1,
        token_mask_rate=0.5,
        feature_mask_rate=0.5,
        edge_drop_rate=0.5,
        seed=3,
    )
    training_config = TrainingConfig(
        epochs=1, patience=1, gradient_accumulation=1, seed=3
    )
    model, pretraining_history = pretrain_model(
        [label_free_graph],
        vocabulary_size=len(vocabulary.itos),
        model_config=model_config,
        pretraining_config=pretraining_config,
        device=torch.device("cpu"),
    )
    model, best_epoch, finetuning_history = finetune_model(
        model,
        [labeled_graph],
        [labeled_graph],
        training_config=training_config,
        device=torch.device("cpu"),
    )
    checkpoint = tmp_path / "pc_stgr_ssl.pt"
    save_checkpoint(
        str(checkpoint),
        model=model,
        vocabulary=vocabulary.to_dict(),
        graph_config=GraphBuildConfig().to_dict(),
        model_config=model_config,
        training_config=training_config,
        pretraining_config=pretraining_config,
        metadata={"model_name": MODEL_NAME, "model_version": MODEL_VERSION},
    )
    loaded, payload = load_checkpoint(str(checkpoint), torch.device("cpu"))
    rankings, diagnostics = predict_graph(
        loaded, label_free_graph, torch.device("cpu"), top_k=2
    )

    assert isinstance(loaded, SelfSupervisedPathConditionedGraphRanker)
    assert payload["format_version"] == CHECKPOINT_FORMAT
    assert payload["pretraining_config"]["epochs"] == 1
    assert len(pretraining_history) == 1
    assert best_epoch == 1
    assert len(finetuning_history) == 1
    assert len(rankings) == 2
    assert {item["ip"] for item in rankings} == set(label_free_graph.device_ips)
    assert "normalized_entropy" in diagnostics


def test_ssl_cli_defaults_and_stage2_result_contract():
    args = build_parser().parse_args(["crossval"])
    assert args.pretrain_epochs == 40
    assert args.pretrain_token_mask_rate == 0.25
    assert args.pretrain_feature_mask_rate == 0.20
    assert args.pretrain_edge_drop_rate == 0.15

    rankings = [
        {"rank": 1, "ip": "D1", "combined_score": 0.7},
        {"rank": 2, "ip": "D2", "combined_score": 0.3},
    ]
    record = result_record(
        _case(),
        rankings,
        {"normalized_entropy": 0.2},
        evaluation_mode="out_of_fold",
        fold=2,
    )
    assert record["stage1"]["model_name"] == MODEL_NAME
    assert record["stage1"]["method"] == MODEL_VERSION
    assert record["stage1"]["pretraining"] == "self_supervised"
    assert record["initial_root_rankings"] == rankings


def test_fold_pretraining_selection_excludes_validation_and_removes_labels():
    labeled_train = _case("train-case")
    label_free_train = _case("train-case", label=None)
    label_free_validation = _case("validation-case", label=None)
    index = {
        os.path.normcase(os.path.normpath("train-case")): label_free_train,
        os.path.normcase(os.path.normpath("validation-case")): label_free_validation,
    }

    selected = _without_labels([labeled_train], index)

    assert selected == [label_free_train]
    assert selected[0].gt_ip is None
    assert label_free_validation not in selected
