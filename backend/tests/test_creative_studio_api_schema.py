from app.api.v1.generation import CreativeStudioChatRequest


def test_chat_request_accepts_editor_only_proof_role():
    request = CreativeStudioChatRequest(
        messages=[{"role": "user", "content": "Use the uploaded proof card."}],
        reference_assets=[
            {"url": "/files/test/proof-a.png", "role": "proof"},
            {"url": "/files/test/proof-b.png", "role": "proof"},
        ],
    )

    assert [asset.role for asset in request.reference_assets] == ["proof", "proof"]
