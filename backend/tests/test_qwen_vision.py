import pytest
from app.qwen_vision import parse_counts
from app.vision_metrics import summarize

def test_qwen_valid_counts_include_unknown():
    data = parse_counts('{"bicycle":10,"powered_two_wheeler":100,"uncertain_type":10,"total":120,"person":3}')
    result = summarize([{'bicycle':data['bicycle'],'motorcycle':data['powered_two_wheeler'],'uncertain_type':data['uncertain_type'],'person':3}],100,50)
    assert result['two_wheeler']['latest']['percent'] == 120
    assert result['uncertain_type']['latest']['count'] == 10

@pytest.mark.parametrize('body', [
    '{"bicycle":1,"powered_two_wheeler":2,"uncertain_type":0,"total":4,"person":0}',
    '{"bicycle":true,"powered_two_wheeler":2,"uncertain_type":0,"total":3,"person":0}',
    '{"bicycle":-1,"powered_two_wheeler":2,"uncertain_type":0,"total":1,"person":0}',
])
def test_qwen_rejects_invalid_counts(body):
    with pytest.raises(ValueError): parse_counts(body)
