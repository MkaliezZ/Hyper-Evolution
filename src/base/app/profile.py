"""Edit SubjectFields to add your application's typed profile fields. No registry."""
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SubjectFields(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    # Example: preferred_topic: str = Field(default='', max_length=200)


class LearningProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    goal: str = Field(default='', max_length=2000)
    prior_experience: str = Field(default='', max_length=2000)
    stage: str = Field(default='', max_length=200)
    schedule: str = Field(default='', max_length=500)
    resources: list[str] = Field(default_factory=list, max_length=30)
    progress_note: str = Field(default='', max_length=2000)
    extensions: SubjectFields = Field(default_factory=SubjectFields)


def validate_profile(value):
    try:
        result = LearningProfile.model_validate(value)
        if any(not item.strip() or len(item) > 500 for item in result.resources):
            raise ValueError('档案resources：每项须为1至500字')
        return result.model_dump()
    except ValidationError as error:
        fields = ', '.join('.'.join(str(p) for p in item['loc']) for item in error.errors())
        raise ValueError('学习档案字段不符，请检查app/profile.py：' + fields) from None
