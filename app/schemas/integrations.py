from pydantic import BaseModel, ConfigDict


class CustomDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str


class DeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    production: bool = True


class GitHubImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    repository_names: list[str]


class LinkedInImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    headline: str = ""
    bio: str = ""
    skills: list[str] = []
    experiences: list[dict] = []
    education_text: str = ""
