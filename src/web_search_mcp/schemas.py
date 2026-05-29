from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Search query",
        min_length=1,
        max_length=300,
    )
    max_results: Optional[int] = Field(
        default=5,
        description="Max results to return (1-10)",
        ge=1,
        le=10,
    )
    fetch_content: Optional[bool] = Field(
        default=True,
        description="If True (default), extract full content from each page",
    )
    max_chars_per_result: Optional[int] = Field(
        default=4000,
        description="Max chars per page (500-10000)",
        ge=500,
        le=10000,
    )
    depth: Optional[str] = Field(
        default="standard",
        description="Depth: 'quick', 'standard' (default), 'deep'",
    )
    purpose: Optional[str] = Field(
        default="answer",
        description="Purpose: 'answer', 'verify', 'complement', 'current_info', 'sources', 'explore'",
    )
    search_context: Optional[str] = Field(
        default=None,
        description="Additional context to refine search queries",
        max_length=500,
    )


class LinkSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description="Search query",
        min_length=1,
        max_length=300,
    )
    max_results: Optional[int] = Field(
        default=5,
        description="Number of results to return (1-10)",
        ge=1,
        le=10,
    )


class FetchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    url: str = Field(
        ...,
        description="Full URL to read",
        min_length=10,
    )
    max_chars: Optional[int] = Field(
        default=4000,
        description="Max chars to return (100-10000)",
        ge=100,
        le=10000,
    )


class MultiSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    queries: list[str] = Field(
        ...,
        description="List of search queries to run in parallel",
        min_length=1,
        max_length=5,
    )
    max_results_per_query: Optional[int] = Field(
        default=3,
        description="Results per query (1-5)",
        ge=1,
        le=5,
    )
