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
    texts = re.split(r'\$(.*?)\$', txt) # FIXME: should split to include '\$'s as well and then below we could check them and then remove them before converting
    for i, txt in enumerate(texts):
        if i % 2 == 0: # FIXME: this is input dependent!!! or is it?
            p.add_run(txt)
        else:
            p._element.append(get_math_oxml(txt))
