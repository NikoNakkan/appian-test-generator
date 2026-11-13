"""Process extraction and hashing on a hand-written process model."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from atg.model import FlowKind
from atg.read import process
from atg.read.hashing import content_hash

PM = """<processModelHaul xmlns:a="http://www.appian.com/ae/types/2009">
<versionUuid>{version}</versionUuid>
<process_model_port xmlns="http://www.appian.com/ae/types/2009"><pm>
<meta><uuid>0002ebd5-feab-8000-684c-7f0000014e7a</uuid>
  <name><string-map><pair><value>Approve</value></pair></string-map></name></meta>
<nodes>
 <node uuid="n1"><guiId>1</guiId>
  <fname><string-map><pair><value>Send?</value></pair></string-map></fname>
  <ac><local-id>core.4</local-id><name>XOR</name><acps>
   <acp name="defaultNode"><a:value>3</a:value></acp>
   <acp name="rules"><a:value><a:acps><a:acp name="rule"><a:value><a:acps>
     <a:acp name="expression"><a:expr>{condition}</a:expr></a:acp>
     <a:acp name="node"><a:value>2</a:value></a:acp>
     <a:acp name="label"><a:value>Yes</a:value></a:acp>
   </a:acps></a:value></a:acp></a:acps></a:value></acp>
  </acps></ac>
  <connections><connection><guiId>9</guiId><to>2</to><flowLabel/></connection>
   <connection><guiId>10</guiId><to>3</to><flowLabel/></connection></connections>
 </node>
 <node uuid="n2"><guiId>2</guiId><ac><local-id>core.1</local-id><name>End Node</name></ac></node>
 <node uuid="n3"><guiId>3</guiId><ac><local-id>core.1</local-id><name>End Node</name></ac></node>
</nodes></pm></process_model_port></processModelHaul>"""


def _pm(version: str = "v1", condition: str = "=pv!submitted") -> ET.Element:
    return ET.fromstring(PM.format(version=version, condition=condition))


def test_identity_nodes_connections_and_gateway() -> None:
    pm = process.find_pm(_pm())
    assert pm is not None
    assert process.pm_identity(pm) == ("0002ebd5-feab-8000-684c-7f0000014e7a", "Approve")
    nodes, flows = process.extract(pm)
    assert next((n.gui_id, n.type_id, n.label) for n in nodes) == (1, "core.4", "Send?")
    by_kind = {f.kind: f for f in flows}
    assert sum(f.kind is FlowKind.CONNECTION for f in flows) == 2
    rule = by_kind[FlowKind.GATEWAY_RULE]
    assert (rule.to_gui, rule.condition, rule.label) == (2, "=pv!submitted", "Yes")
    assert by_kind[FlowKind.GATEWAY_DEFAULT].to_gui == 3


def test_hash_ignores_version_stamp_but_not_logic() -> None:
    base = content_hash(_pm())
    assert content_hash(_pm(version="v2")) == base
    assert content_hash(_pm(condition="=not(pv!submitted)")) != base
