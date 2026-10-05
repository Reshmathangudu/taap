import base64
import io
import json

import pytest
from docx import Document

from agents.test_case_agent import context_extraction as ctx
from agents.test_case_agent.models import SupplementalContext


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# NONE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_none_source_type_is_a_noop():
    result = await ctx.process_supplemental_context(SupplementalContext())
    assert result.source_type == "NONE"
    assert result.extracted_text is None
    assert result.transcript is None
    assert result.content_base64 is None


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_html_raw_html_is_extracted_and_scripts_stripped():
    html = """
    <html><head><style>.x{color:red}</style><script>alert(1)</script></head>
    <body>
      <h1>OTP Verification</h1>
      <input placeholder="Enter OTP"/>
      <button aria-label="Submit OTP"></button>
      <p>You have <strong>3</strong> attempts remaining.</p>
      <!-- a stray comment -->
    </body></html>
    """
    result = await ctx.process_supplemental_context(
        SupplementalContext(source_type="HTML", raw_html=html)
    )

    assert result.source_type == "HTML"
    assert result.content_base64 is None
    assert result.raw_html is None
    assert "alert(1)" not in result.extracted_text
    assert "color:red" not in result.extracted_text
    assert "a stray comment" not in result.extracted_text
    assert "OTP Verification" in result.extracted_text
    assert "Enter OTP" in result.extracted_text
    assert "Submit OTP" in result.extracted_text
    assert "attempts remaining" in result.extracted_text


@pytest.mark.asyncio
async def test_html_base64_is_decoded_then_extracted():
    html = "<p>Password must be at least 8 characters.</p>"
    result = await ctx.process_supplemental_context(
        SupplementalContext(source_type="HTML", content_base64=_b64(html.encode("utf-8")))
    )
    assert result.content_base64 is None
    assert "Password must be at least 8 characters." in result.extracted_text


@pytest.mark.asyncio
async def test_html_empty_content_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(SupplementalContext(source_type="HTML"))
    assert exc_info.value.code == "EMPTY_CONTENT"


@pytest.mark.asyncio
async def test_html_no_meaningful_text_raises_extraction_failed():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="HTML",
                raw_html="<script>alert(1)</script><style>.a{}</style>",
            )
        )
    assert exc_info.value.code == "EXTRACTION_FAILED"


# ---------------------------------------------------------------------------
# FILE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_txt_extraction():
    content = "Max login attempts is configurable per tenant.".encode("utf-8")
    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE",
            file_name="notes.txt",
            content_base64=_b64(content),
        )
    )
    assert result.content_base64 is None
    assert result.extracted_text == "Max login attempts is configurable per tenant."


@pytest.mark.asyncio
async def test_file_markdown_extraction():
    content = "# OTP Flow\n\n- Max attempts: see business rules".encode("utf-8")
    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE", file_name="spec.md", content_base64=_b64(content)
        )
    )
    assert "# OTP Flow" in result.extracted_text


@pytest.mark.asyncio
async def test_file_json_extraction_pretty_prints_and_rejects_invalid():
    valid = json.dumps({"max_attempts": 3}).encode("utf-8")
    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE", file_name="data.json", content_base64=_b64(valid)
        )
    )
    assert "max_attempts" in result.extracted_text
    assert "3" in result.extracted_text

    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="FILE",
                file_name="bad.json",
                content_base64=_b64(b"{not valid json"),
            )
        )
    assert exc_info.value.code == "EXTRACTION_FAILED"


@pytest.mark.asyncio
async def test_file_csv_extraction():
    content = "field,limit\nmax_attempts,3\nmin_length,8\n".encode("utf-8")
    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE", file_name="limits.csv", content_base64=_b64(content)
        )
    )
    assert "field | limit" in result.extracted_text
    assert "max_attempts | 3" in result.extracted_text


@pytest.mark.asyncio
async def test_file_html_extension_reuses_html_extraction():
    content = "<p>Field label: Account Number</p>".encode("utf-8")
    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE", file_name="page.html", content_base64=_b64(content)
        )
    )
    assert "Field label: Account Number" in result.extracted_text


@pytest.mark.asyncio
async def test_file_docx_extraction_reaches_normalized_input():
    document = Document()
    document.add_paragraph("Retry lockout applies after repeated failures.")
    buffer = io.BytesIO()
    document.save(buffer)

    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE",
            file_name="spec.docx",
            content_base64=_b64(buffer.getvalue()),
        )
    )
    assert result.content_base64 is None
    assert "Retry lockout applies after repeated failures." in result.extracted_text


@pytest.mark.asyncio
async def test_file_pdf_extraction_uses_pypdf_and_joins_pages(monkeypatch):
    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakeReader:
        def __init__(self, _stream):
            self.pages = [_FakePage("Page one text."), _FakePage("Page two text.")]

    monkeypatch.setattr(ctx, "PdfReader", _FakeReader)

    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="FILE",
            file_name="doc.pdf",
            content_base64=_b64(b"%PDF-1.4 fake"),
        )
    )
    assert "Page one text." in result.extracted_text
    assert "Page two text." in result.extracted_text


@pytest.mark.asyncio
async def test_file_pdf_corrupt_bytes_raise_extraction_failed():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="FILE",
                file_name="broken.pdf",
                content_base64=_b64(b"not a real pdf"),
            )
        )
    assert exc_info.value.code == "EXTRACTION_FAILED"


@pytest.mark.asyncio
async def test_file_unsupported_format_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="FILE",
                file_name="archive.zip",
                mime_type="application/zip",
                content_base64=_b64(b"PK\x03\x04"),
            )
        )
    assert exc_info.value.code == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_file_missing_content_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(source_type="FILE", file_name="notes.txt")
        )
    assert exc_info.value.code == "MISSING_CONTENT"


@pytest.mark.asyncio
async def test_file_empty_content_raises():
    # Base64 of zero bytes is an empty string, which is indistinguishable
    # from "no content_base64 provided" — both are rejected up front.
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="FILE", file_name="notes.txt", content_base64=_b64(b"")
            )
        )
    assert exc_info.value.code == "MISSING_CONTENT"


@pytest.mark.asyncio
async def test_file_oversized_content_raises(monkeypatch):
    monkeypatch.setattr(ctx, "MAX_FILE_BYTES", 10)
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="FILE",
                file_name="notes.txt",
                content_base64=_b64(b"x" * 100),
            )
        )
    assert exc_info.value.code == "OVERSIZED_CONTENT"


def test_invalid_base64_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        ctx._decode_base64("not-valid-base64!!!")
    assert exc_info.value.code == "INVALID_BASE64"


# ---------------------------------------------------------------------------
# AUDIO
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audio_transcription_is_mocked_and_base64_cleared(monkeypatch):
    class _FakeTranscription:
        text = "User says max retries is three."

    async def _fake_atranscription(*, model, file):
        assert model == ctx.AUDIO_MODEL_NAME
        assert file.name  # the SDK relies on this for format sniffing
        return _FakeTranscription()

    monkeypatch.setattr(ctx.litellm, "atranscription", _fake_atranscription)

    result = await ctx.process_supplemental_context(
        SupplementalContext(
            source_type="AUDIO",
            file_name="walkthrough.mp3",
            mime_type="audio/mpeg",
            content_base64=_b64(b"fake-audio-bytes"),
        )
    )

    assert result.content_base64 is None
    assert result.transcript == "User says max retries is three."


@pytest.mark.asyncio
async def test_audio_transcription_failure_raises(monkeypatch):
    async def _raise(*_args, **_kwargs):
        raise RuntimeError("upstream transcription API error")

    monkeypatch.setattr(ctx.litellm, "atranscription", _raise)

    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="AUDIO",
                file_name="clip.mp3",
                content_base64=_b64(b"fake-audio-bytes"),
            )
        )
    assert exc_info.value.code == "TRANSCRIPTION_FAILED"


@pytest.mark.asyncio
async def test_audio_unsupported_mime_type_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(
            SupplementalContext(
                source_type="AUDIO",
                mime_type="video/mp4",
                content_base64=_b64(b"fake-audio-bytes"),
            )
        )
    assert exc_info.value.code == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_audio_missing_content_raises():
    with pytest.raises(ctx.SupplementalContextError) as exc_info:
        await ctx.process_supplemental_context(SupplementalContext(source_type="AUDIO"))
    assert exc_info.value.code == "MISSING_CONTENT"
