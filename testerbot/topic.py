"""Keeping a focused crawl focused.

Every website links outward to things that have nothing to do with its subject:
its CMS vendor, its events platform, the newswire it publishes through, its job
board, a government press release it cites. Follow those links far enough and a
crawl that started in fintech is reading astrophysics listings and meetup pages
- and the "index of your field" is no longer an index of your field.

This module is the gate. A candidate domain must show some sign of belonging to
the subject before the crawl spends its budget going deeper, and the evidence is
kept cheap: the words in the links that point at it, and the words on the one
page we have to fetch anyway.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

# B2B plumbing every company links to regardless of what it does. These are not
# "utility" in the footer-social sense - they are real businesses - but a link
# to them says nothing about the linking site's subject, so they must not pull
# a focused crawl off course.
INFRASTRUCTURE_DOMAINS = {
    # hiring
    "myworkdayjobs.com", "workday.com", "greenhouse.io", "lever.co",
    "smartrecruiters.com", "workable.com", "bamboohr.com", "jobvite.com",
    "icims.com", "taleo.net", "successfactors.com", "ashbyhq.com",
    "cryptojobslist.com", "efinancialcareers.com", "web3.career",
    "cryptocurrencyjobs.co", "indeed.com", "glassdoor.com",
    # events and webinars
    "cvent.com", "cvent.me", "cventevents.com", "eventbrite.com", "hopin.com",
    "goldcast.io", "on24.com", "zoom.us", "gotowebinar.com", "bigmarker.com",
    "luma.com", "lu.ma", "meetup.com", "sessionize.com",
    "iqpc.com", "informa.com", "ibc-asia.com", "arena-international.com",
    "bc.events", "blockchainlive.com", "iblockchainsummit.com",
    # newswires and press distribution
    "prnewswire.com", "businesswire.com", "globenewswire.com", "prweb.com",
    "einpresswire.com", "accesswire.com", "newswire.com", "buysub.com",
    # analyst, review and marketing platforms
    "gartner.com", "forrester.com", "g2.com", "capterra.com", "trustradius.com",
    "trustpilot.com", "clutch.co", "softwareadvice.com",
    "futuremarketinsights.com", "marketsandmarkets.com",
    "grandviewresearch.com", "statista.com", "mordorintelligence.com",
    # website / CMS / SaaS vendors linked from "powered by" and docs
    "sitecore.com", "outsystems.com", "qlik.com", "salesforce.com", "hubspot.com",
    "marketo.com", "pardot.com", "wix.com", "squarespace.com", "webflow.com",
    "shopify.com", "drupal.org", "contentful.com", "blueprism.com",
    "site.com", "force.com", "sharepoint.com", "atlassian.net",
    # code and docs hosts
    "github.com", "gitlab.com", "bitbucket.org", "readthedocs.io", "npmjs.com",
    "pypi.org", "stackoverflow.com", "arxiv.org", "doi.org", "researchgate.net",
    # general news and government that everyone cites but nobody is "in"
    "nytimes.com", "wsj.com", "washingtonpost.com", "bbc.co.uk", "cnn.com",
    "whitehouse.gov", "usa.gov", "justice.gov", "congress.gov", "govinfo.gov",
    "artnews.com", "forbesmagazine.com",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower())


class TopicFilter:
    """Decides whether a domain looks like it belongs to the subject.

    `min_hits` is how many *distinct* subject terms a page must show. One is
    too easy: a gaming site that mentions "blockchain" once in a news story
    passes, and the crawl then spends twenty-five pages on Elden Ring. Two
    distinct terms is a much better line, because a site that is really in the
    field uses several of its words and a site that is not rarely uses two.

    A filter with no terms lets everything through, so behaviour is unchanged
    unless the user asks for focus.
    """

    def __init__(self, terms: Optional[Sequence[str]] = None,
                 min_hits: int = 2) -> None:
        self.terms: List[str] = []
        for t in terms or []:
            t = _norm(t).strip()
            if t:
                self.terms.append(t)
        self.min_hits = max(1, min_hits)

    def __bool__(self) -> bool:
        return bool(self.terms)

    def hits(self, text: str) -> List[str]:
        """Which subject terms appear in this text.

        Terms that contain another matched term are not counted again -
        "payment" and "payments" are one sign, not two, and counting them
        twice would let a single mention clear a threshold of two.
        """
        if not self.terms:
            return []
        hay = _norm(text)
        found = sorted((t for t in self.terms if t in hay), key=len)
        out: List[str] = []
        for t in found:
            if not any(shorter in t for shorter in out):
                out.append(t)
        return out

    def matches(self, text: str) -> bool:
        if not self.terms:
            return True          # no subject given: everything is in scope
        return len(self.hits(text)) >= self.min_hits

    @staticmethod
    def is_infrastructure(domain: str) -> bool:
        d = (domain or "").lower()
        if d.startswith("www."):
            d = d[4:]
        return d in INFRASTRUCTURE_DOMAINS

    @classmethod
    def from_file(cls, path: str, min_hits: int = 2) -> "TopicFilter":
        with open(path, encoding="utf-8") as fh:
            terms = [line.strip() for line in fh
                     if line.strip() and not line.startswith("#")]
        return cls(terms, min_hits)
