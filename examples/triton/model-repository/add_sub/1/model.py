# Triton Python backend example.
# This model receives two FP32 tensors and returns their elementwise sum and difference.

import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    def initialize(self, args):
        # Parse model config if needed.
        self.model_config = args.get("model_config")

    def execute(self, requests):
        responses = []
        for request in requests:
            a = pb_utils.get_input_tensor_by_name(request, "INPUT0").as_numpy()
            b = pb_utils.get_input_tensor_by_name(request, "INPUT1").as_numpy()

            out0 = a + b
            out1 = a - b

            t0 = pb_utils.Tensor("OUTPUT0", out0.astype(np.float32))
            t1 = pb_utils.Tensor("OUTPUT1", out1.astype(np.float32))
            responses.append(pb_utils.InferenceResponse(output_tensors=[t0, t1]))
        return responses

    def finalize(self):
        # Called when the model is unloaded.
        return
