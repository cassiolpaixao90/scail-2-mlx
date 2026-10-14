"""Exercise the production segment loop without downloading/loading any weights."""
from types import SimpleNamespace

import mlx.core as mx
import pytest

from scail2_mlx.scail import SCAIL2Pipeline


@pytest.mark.parametrize('count', [2, 65, 82, 158, 198])
def test_pipeline_retains_partial_tail_and_history(count):
    encoded_lengths = []
    histories = []

    class VAE:
        def encode(self, videos):
            encoded_lengths.extend(v.shape[1] for v in videos)
            return [mx.zeros((16, (v.shape[1]-1)//4+1, v.shape[2]//8, v.shape[3]//8))
                    for v in videos]

        def decode(self, zs):
            return [mx.zeros((3, (z.shape[1]-1)*4+1, z.shape[2]*8, z.shape[3]*8)) for z in zs]

    def model(xs, **kwargs):
        histories.append(kwargs['history_mask'] is not None)
        return [mx.zeros_like(x) for x in xs]

    pipe = SCAIL2Pipeline.__new__(SCAIL2Pipeline)
    pipe.vae = VAE()
    pipe.vae_stride = (4,8,8)
    pipe.num_train_timesteps = 1000
    pipe.text_encoder = lambda prompts: [mx.zeros((1,4)) for _ in prompts]
    pipe.clip = SimpleNamespace(visual=lambda images: mx.zeros((1,1,4)))
    pipe.model = model
    pipe.evict_encoders = True
    result = pipe.generate('test', mx.zeros((3,32,32)), mx.zeros((3,32,32)),
        mx.zeros((count,3,32,32)), mx.zeros((3,count,32,32)), True,
        sample_solver='dpm++', sampling_steps=1, guide_scale=1, cache_limit_bytes=0)
    mx.eval(result)
    assert result.shape == (3,count,32,32)
    assert all((n-1)%4 == 0 for n in encoded_lengths)
    assert histories[0] is False
    if count > 81:
        assert all(histories[1:])
    if count == 198:
        assert encoded_lengths == [1,81,81,5,49,5]
