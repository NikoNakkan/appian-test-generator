"""Layers 2-4 on top of Layer 1, run in order by pipeline.run_layers, each proved by checks/.

pipeline         one export root through every layer, saving results and check outcomes
layer2_sail      parse every SAIL expression, store decision points (branches)
layer3_paths     enumerate test paths through each process model (uses path_engine)
layer4_features  group entry points and what they reach into features (uses feature_engine)
path_engine      pure path enumeration over a process graph (gateways, loops, pruning)
feature_engine   dependency graph, reach from an entry point, feature building
checks/          automatic checks per layer (layer1..layer4), raw counts from the files
"""
