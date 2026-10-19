import base64
import io
import json
import urllib.error

import pytest

from spatialguard_api import classifier, insights


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return io.BytesIO(json.dumps(self.value).encode())

    def __exit__(self, *args):
        return False


def completed(label="delivery_activity"):
    proposal = {
        "label": label,
        "confidence": "medium",
        "summary": "A person appears to be placing a parcel near the entrance.",
        "visible_evidence": ["Parcel-shaped object", "Person near the doorway"],
        "uncertainty": "Uniform and delivery markings are not readable.",
    }
    return {"output": {"message": {"role": "assistant", "content": [{"text": json.dumps(proposal)}]}},
            "usage": {"inputTokens": 1200, "outputTokens": 90}}


def configure(monkeypatch):
    monkeypatch.setattr(insights, "_settings", lambda: {
        "AWS_BEARER_TOKEN_BEDROCK": "server-secret", "AWS_REGION": "us-west-2",
        "PATHLIGHT_INSIGHT_MODEL": insights.DEFAULT_MODEL})
    monkeypatch.delenv("PATHLIGHT_CLASSIFIER_MODEL", raising=False)


def images_in(payload):
    return [base64.b64decode(part["image"]["source"]["bytes"])
            for part in payload["messages"][0]["content"] if "image" in part]


def test_bedrock_request_sends_the_snapshot_and_reads_a_structured_label(monkeypatch):
    configure(monkeypatch)
    captured = {}

    def open_request(request, timeout):
        captured.update(url=request.full_url, payload=json.loads(request.data), timeout=timeout,
                        auth=request.get_header("Authorization"))
        return Response(completed())

    monkeypatch.setattr(classifier.urllib.request, "urlopen", open_request)
    result = classifier.classify_image(b"jpeg-bytes", "image/jpeg")
    assert captured["url"].startswith("https://bedrock-runtime.us-west-2.amazonaws.com/model/")
    assert captured["url"].endswith("/converse")
    assert captured["auth"] == "Bearer server-secret"
    assert "server-secret" not in json.dumps(captured["payload"])
    content = captured["payload"]["messages"][0]["content"]
    assert content[1]["image"]["format"] == "jpeg" and images_in(captured["payload"]) == [b"jpeg-bytes"]
    assert "JSON schema" in content[0]["text"]
    assert result.label == "delivery_activity"
    assert result.display_label == "Possible delivery"
    assert result.model == insights.DEFAULT_MODEL


def test_provider_errors_never_expose_response_body(monkeypatch):
    configure(monkeypatch)

    def denied(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://bedrock-runtime.us-west-2.amazonaws.com", 401, "denied", {},
            io.BytesIO(b"server-secret must never be returned"))

    monkeypatch.setattr(classifier.urllib.request, "urlopen", denied)
    with pytest.raises(classifier.ClassifierUnavailable) as error:
        classifier.classify_image(b"jpeg-bytes", "image/jpeg")
    assert "server-secret" not in str(error.value)
    assert "rejected" in str(error.value)


def test_unreadable_model_output_is_refused(monkeypatch):
    configure(monkeypatch)
    reply = {"output": {"message": {"content": [{"text": "Sorry, I cannot help with that."}]}}}
    monkeypatch.setattr(classifier.urllib.request, "urlopen", lambda request, timeout: Response(reply))
    with pytest.raises(classifier.ClassifierUnavailable, match="unreadable"):
        classifier.classify_image(b"jpeg-bytes", "image/jpeg")


def test_unconfigured_server_says_so(monkeypatch):
    monkeypatch.setattr(insights, "_settings", lambda: {
        "AWS_BEARER_TOKEN_BEDROCK": "", "AWS_REGION": "us-west-2", "PATHLIGHT_INSIGHT_MODEL": insights.DEFAULT_MODEL})
    assert classifier.status() == {"configured": False, "model": insights.DEFAULT_MODEL}
    with pytest.raises(classifier.ClassifierUnavailable, match="not configured"):
        classifier.classify_image(b"jpeg-bytes", "image/jpeg")


def test_sequence_preserves_frame_order_and_uses_one_request(monkeypatch):
    configure(monkeypatch)
    captured = []

    def open_request(request, timeout):
        captured.append(json.loads(request.data))
        return Response(completed())

    monkeypatch.setattr(classifier.urllib.request, "urlopen", open_request)
    result = classifier.classify_images([b"first", b"second"], "image/jpeg")
    assert result.label == "delivery_activity"
    assert len(captured) == 1
    assert "chronological order" in captured[0]["messages"][0]["content"][0]["text"]
    assert images_in(captured[0]) == [b"first", b"second"]


def test_sequence_rejects_unbounded_or_empty_input(monkeypatch):
    configure(monkeypatch)
    for images in ([], [b"x"] * 7, [b"valid", b""]):
        with pytest.raises(classifier.ClassifierUnavailable):
            classifier.classify_images(images, "image/jpeg")


def test_ring_watermark_is_preserved_and_excluded_from_scene_evidence(monkeypatch):
    """The classifier receives the full provider image, including both top corners."""
    configure(monkeypatch)
    captured = {}
    image = b"ring-watermark-top-left|device-app-time-top-right|scene-pixels"

    def open_request(request, timeout):
        captured["payload"] = json.loads(request.data)
        return Response(completed("no_relevant_activity"))

    monkeypatch.setattr(classifier.urllib.request, "urlopen", open_request)
    classifier.classify_image(image, "image/jpeg")
    assert images_in(captured["payload"]) == [image]
    text = captured["payload"]["messages"][0]["content"][0]["text"]
    assert "Treat that watermark as" in text
    assert "never classify its logo" in text
