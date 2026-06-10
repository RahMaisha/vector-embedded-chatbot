"""
Language detection utility for vector metadata.
Detects language from filenames, URLs, or explicit tags.

Supported languages:
  - "en" — English
  - "ben" or "bn" — Bengali
  - "es" — Spanish
  - "fr" — French
  - ... (easily extendable)
"""

import re
from typing import Optional


def detect_language_from_filename(filename: str) -> str:
    """
    Extract language code from filename using patterns:
      - my_document_en.pdf → "en"
      - pregnancy_guide_ben.pdf → "ben"
      - document.pdf → "en" (default)
    """
    filename_lower = filename.lower()
    
    # Pattern 1: _XX or -XX at end (e.g., "_en", "-ben", "_bn")
    match = re.search(r'[_-](en|english|es|spanish|fr|french|ben|bengali|bn|bn-IN)(?:\.|$)', filename_lower)
    if match:
        lang_code = match.group(1)
        return normalize_language_code(lang_code)
    
    # Pattern 2: xxlang, xxen, xxben in filename
    if (
        'bengali' in filename_lower
        or '_ben' in filename_lower
        or '-ben' in filename_lower
        or 'benpdf' in filename_lower
        or '_bn' in filename_lower
        or '-bn' in filename_lower
        or 'bnpdf' in filename_lower
    ):
        return "ben"
    if 'english' in filename_lower or '_en' in filename_lower or '-en' in filename_lower:
        return "en"
    if 'spanish' in filename_lower or '_es' in filename_lower or '-es' in filename_lower:
        return "es"
    if 'french' in filename_lower or '_fr' in filename_lower or '-fr' in filename_lower:
        return "fr"
    
    # Default to English
    return "en"


def detect_language_from_url(url: str) -> str:
    """
    Extract language code from URL patterns:
      - .com/en/ → "en"
      - .com/bn/ → "ben"
      - .com/es/ → "es"
    """
    url_lower = (url or "").lower()

    # ── Explicit keyword signals first ─────────────────────────
    # Many sites (especially country or topic pages) include clear
    # signals that imply Bengali even when the path contains other
    # short tokens like 'org' that would confuse the regex.
    bengali_signals = [
        'bangladesh',
        '/bn/',
        '/ben/',
        'bangla',
        'parenting-bd',
        'bd/',
        'bn/',
    ]
    if any(signal in url_lower for signal in bengali_signals):
        return 'ben'

    # Pattern: /en/, /es/, /fr/, /ben/, /bn/ in path
    match = re.search(r'/([a-z]{2,5})(?:/|$)', url_lower)
    if match:
        lang_code = match.group(1)
        if lang_code in ('en', 'es', 'fr', 'de', 'pt', 'bg'):
            return normalize_language_code(lang_code)
        if lang_code in ('ben', 'bn', 'bn-in'):
            return 'ben'

    # Default to English
    return 'en'


def detect_language_from_text(text: str) -> str:
    """
    Detect language from text content based on script frequency.
    This helps tag OCR-extracted Bengali chunks even when filenames
    or URLs do not include an explicit language marker.
    """
    text = text or ""
    bengali_chars = sum(1 for c in text if '\u0980' <= c <= '\u09FF')
    if bengali_chars > max(5, len(text) * 0.05):
        return 'ben'
    return 'en'


def normalize_language_code(code: str) -> str:
    """
    Normalize language code to standard format:
      - "bengali", "bn", "bn-IN" → "ben"
      - "english", "eng" → "en"
      - etc.
    """
    code = code.lower().strip()
    
    # Bengali variants
    if code in ('bengali', 'bn', 'bn-in', 'bn_in', 'bengali'):
        return "ben"
    
    # English variants
    if code in ('english', 'eng'):
        return "en"
    
    # Direct 2-letter codes
    if code in ('en', 'es', 'fr', 'de', 'pt'):
        return code
    
    # If it's already a standard code, return as-is
    return code


def detect_language(
    filename: Optional[str] = None,
    url: Optional[str] = None,
    text: Optional[str] = None,
    explicit_lang: Optional[str] = None
) -> str:
    """
    Main function to detect language with priority:
    1. Explicit language (if provided)
    2. From filename (if provided)
    3. From URL (if provided)
    4. Default to "en"
    """
    if explicit_lang:
        return normalize_language_code(explicit_lang)

    if text:
        lang = detect_language_from_text(text)
        if lang != 'en':
            return lang
    
    if filename:
        lang = detect_language_from_filename(filename)
        if lang != "en":  # If not default, we found it
            return lang
    
    if url:
        lang = detect_language_from_url(url)
        if lang != "en":  # If not default, we found it
            return lang
    
    # Default
    return "en"


# Test examples
if __name__ == "__main__":
    test_cases = [
        ("pregnancy_guide_en.pdf", None, None),
        ("health_ben.pdf", None, None),
        ("document_bn.pdf", None, None),
        ("bangla_health_guide.pdf", None, None),
        ("random_doc.pdf", None, None),
        ("test.pdf", "https://example.com/bn/page", None),
        (None, "https://nhs.uk/en/pregnancy", None),
        ("file.pdf", None, "bengali"),
        ("file.pdf", None, "bn-IN"),
    ]
    
    print("Language Detection Examples:")
    print("=" * 70)
    for filename, url, explicit in test_cases:
        result = detect_language(filename, url, explicit)
        print(f"  File: {filename!r:30} URL: {url!r:35} → {result!r}")
