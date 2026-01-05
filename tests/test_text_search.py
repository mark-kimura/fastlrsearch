"""Unit tests for text_search module."""

import pytest
from fastlrsearch.search.text_search import normalize_query, _escape_fts_word


class TestEscapeFtsWord:
    """Tests for _escape_fts_word function."""

    def test_simple_word(self):
        """Simple words should pass through unchanged."""
        assert _escape_fts_word("dog") == "dog"
        assert _escape_fts_word("cat") == "cat"
        assert _escape_fts_word("sunset") == "sunset"

    def test_word_with_comma(self):
        """Words with commas should be quoted."""
        assert _escape_fts_word("dog,") == '"dog,"'
        assert _escape_fts_word(",cat") == '",cat"'

    def test_word_with_special_chars(self):
        """Words with special FTS5 characters should be quoted."""
        assert _escape_fts_word("c++") == '"c++"'
        assert _escape_fts_word("test-case") == '"test-case"'
        assert _escape_fts_word("it's") == '"it\'s"'
        assert _escape_fts_word("(test)") == '"(test)"'
        assert _escape_fts_word("file.txt") == '"file.txt"'

    def test_word_with_double_quote(self):
        """Double quotes should be escaped by doubling."""
        assert _escape_fts_word('say"hello') == '"say""hello"'


class TestNormalizeQuery:
    """Tests for normalize_query function."""

    def test_simple_query(self):
        """Simple single word query."""
        assert normalize_query("dog") == "dog"
        assert normalize_query("sunset") == "sunset"

    def test_multi_word_query(self):
        """Multi-word queries should work."""
        assert normalize_query("white dog") == "white dog"
        assert normalize_query("sunset on beach") == "sunset on beach"

    def test_comma_in_query(self):
        """Commas should be stripped from query."""
        assert normalize_query("dog, cat") == "dog cat"
        assert normalize_query("red, green, blue") == "red green blue"

    def test_multiple_punctuation(self):
        """Multiple punctuation marks should be handled."""
        assert normalize_query("hello! world?") == "hello world"
        assert normalize_query("test; example: demo") == "test example demo"

    def test_empty_query(self):
        """Empty or whitespace-only query should return empty string."""
        assert normalize_query("") == ""
        assert normalize_query("   ") == ""
        assert normalize_query(",,,") == ""

    def test_preserves_fts_operators(self):
        """FTS5 operators (OR, AND, NOT) should be preserved."""
        assert normalize_query("dog OR cat") == "dog OR cat"
        assert normalize_query("dog AND cat") == "dog AND cat"

    def test_special_chars_in_words(self):
        """Words with special characters should be escaped."""
        result = normalize_query("c++ programming")
        assert '"c++"' in result
        assert "programming" in result

    def test_trailing_comma(self):
        """Trailing comma should not cause issues."""
        assert normalize_query("dog,") == "dog"
        assert normalize_query("cat, ") == "cat"
