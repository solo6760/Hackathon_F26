from qonnx.core.modelwrapper import ModelWrapper
from qonnx.transformation.general import GiveUniqueNodeNames, GiveReadableTensorNames

from finn.transformation.fpgadataflow.insert_dwc import InsertDWC
from finn.transformation.fpgadataflow.specialize_layers import SpecializeLayers
from finn.transformation.fpgadataflow.prepare_ip import PrepareIP
from finn.transformation.fpgadataflow.hlssynth_ip import HLSSynthIP
from finn.transformation.fpgadataflow.replace_verilog_relpaths import ReplaceVerilogRelPaths
from finn.transformation.fpgadataflow.create_stitched_ip import CreateStitchedIP
from finn.util.vivado import parse_ooc_synth_results

MODEL = "/home/evan/Hackathon_F26/testing_py/transformer_layer_folded_1024.onnx"
OUT = "/home/evan/Hackathon_F26/testing_py/transformer_layer_ooc.onnx"

PART = "xck26-sfvc784-2LV-c"
CLK_NS = 10.0

print("Loading model...")
model = ModelWrapper(MODEL)

print("Nodes:")
for n in model.graph.node:
    print(" ", n.name, n.op_type)

print("Preparing hardware...")
model = model.transform(InsertDWC())
model = model.transform(SpecializeLayers(PART))
model = model.transform(GiveUniqueNodeNames())
model = model.transform(GiveReadableTensorNames())

print("Generating IP...")
model = model.transform(PrepareIP(PART, CLK_NS))
model = model.transform(HLSSynthIP())
model = model.transform(ReplaceVerilogRelPaths())

print("Running Vivado synthesis + place-and-route...")
model = model.transform(
    CreateStitchedIP(
        PART,
        CLK_NS,
        run_synth=True,
        run_pnr=True
    )
)

proj = model.get_metadata_prop("vivado_stitch_proj")
print("Vivado project:", proj)

results = parse_ooc_synth_results(proj)

print("\n===== OOC RESULTS =====")
print(results)

model.set_metadata_prop("res_total_ooc_synth", str(results))
model.save(OUT)

print("\nSaved:", OUT)
