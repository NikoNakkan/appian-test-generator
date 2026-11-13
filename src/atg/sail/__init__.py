"""SAIL, Appian's expression language: parse it, print it, show it, and read meaning from it.

ast       Lark grammar -> typed tree (Call, Name, Canon #"...", Str, BinOp, ...); parse()
printer   tree -> text (round-trips), normalised form
walk      walking a tree: nodes(), keyword(call, key), plain_name(fn)
branches  decision points: if / match / and / or / null checks / loops / comparisons
display   canonical names (#"_a-...uuid", urn:appian:record-field:...) -> Designer form
explain   a condition as a short English phrase ("doc is filled in", "a ≠ 2")
actions   what a screen's buttons and links do (submit, start process, write records)
fields    form fields: kind, label, the ri! inputs they set, required, shown sometimes
"""
