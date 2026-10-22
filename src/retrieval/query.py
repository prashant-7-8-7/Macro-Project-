"""Small, local query helpers; no AI request is needed to find search terms."""
import re


_FILLER = set('''a an the is are was were be been being do does did can could
would should may might will have has had of to for from at in on by as with and
or but if than also what which who whose why how when where please explain
describe tell give show write discuss define list outline summarize summarise
summary overview key main important most concept concepts point points finding
findings conclusion conclusions simply simple example examples answer answers
question questions document documents pdf file files selected this that these
those it its me us my our your you about above previous first second third more detail
details detailed briefly brief again same'''.split())


def topic_terms(query):
    # Remove answer-format instructions without discarding technical terms such
    # as "language" or numbers that may themselves name the topic.
    query = re.sub(r'\b(?:in\s+)?(?:simple|plain|easy)\s+(?:language|terms|words)\b', ' ', query, flags=re.I)
    query = re.sub(r'\b(?:2|6|10)[ -]?marks?\b', ' ', query, flags=re.I)
    words = re.findall(r'[^\W_]+', query.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(word for word in words if word not in _FILLER))[:32]


def refers_back(query):
    return bool(re.search(r'\b(it|this|that|these|those|above|previous|same)\b', query, re.I))


def generic_request(query):
    return not topic_terms(query) and bool(re.search(
        r'\b(explain|describe|summari[sz]e|summary|overview|points?|findings?|concepts?|conclusions?|example|more|again)\b',
        query, re.I))


def explicit_document_request(query):
    return bool(re.search(r'\b(documents?|pdf|files?)\b', query, re.I))
