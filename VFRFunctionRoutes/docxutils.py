import re
import os
from pathlib import Path
from latex2mathml.converter import convert as latex2mml
from lxml import etree # pylint: disable=no-name-in-module

_filespath = Path(__file__).parent

def get_math_oxml(latex):
    mmlxml_str = latex2mml(latex)
    tree = etree.fromstring(mmlxml_str)
    xslt = etree.parse(os.path.join(_filespath, 'MML2OMML.XSL'))
    transform = etree.XSLT(xslt)
    mth = transform(tree).getroot()
    return mth


def add_formula_par(doc, txt, **kwargs):
    p = doc.add_paragraph(**kwargs)
    p._element.append(get_math_oxml(txt))
