# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License <http://www.gnu.org/licenses/gpl-3.0.txt>
# for more details.
#
# Copyright (C) 2015  Igor Tkach

import argparse
import os
import re
import sys

from collections import defaultdict

import slob

# original expression from
# http://stackoverflow.com/questions/694344/regular-expression-that-matches-between-quotes-containing-escaped-quotes
# "(?:[^\\"]+|\\.)*"
# some examples don't have closing quote which
# make the subn with this expression hang
# quoted_text = re.compile(r'"(?:[^"]+|\.)*["|\n]')

# make it a capturing group so that we can get rid of quotes
quoted_text = re.compile(r'"([^"]+|\.)*["|\n]')

ref = re.compile(r"`(\w+)'")


import collections


def iterlines(wordnetdir):
    dict_dir = os.path.join(wordnetdir, "dict")
    for name in os.listdir(dict_dir):
        if name.startswith("data."):
            with open(os.path.join(dict_dir, name)) as f:
                for line in f:
                    if not line.startswith("  "):
                        yield line


class SynSet(object):
    def __init__(self, line):
        self.line = line
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        meta, self.gloss = line.split("|")
        self.meta_parts = meta.split()

    @property
    def offset(self):
        return int(self.meta_parts[0])

    @property
    def lex_filenum(self):
        return self.meta_parts[1]

    @property
    def ss_type(self):
        return self.meta_parts[2]

    @property
    def w_cnt(self):
        return int(self.meta_parts[3], 16)

    @property
    def words(self):
        return [self.meta_parts[4 + 2 * i].replace("_", " ") for i in range(self.w_cnt)]

    @property
    def pointers(self):
        p_cnt_index = 4 + 2 * self.w_cnt
        p_cnt = self.meta_parts[p_cnt_index]
        pointer_count = int(p_cnt)
        start = p_cnt_index + 1
        return [
            Pointer(*self.meta_parts[start + i * 4 : start + (i + 1) * 4])
            for i in range(pointer_count)
        ]

    def __repr__(self):
        return "SynSet(%r)" % self.line


class PointerSymbols(object):

    n = {
        "!": "Antonyms",
        "@": "Hypernyms",
        "@i": "Instance hypernyms",
        "~": "Hyponyms",
        "~i": "Instance hyponyms",
        "#m": "Member holonyms",
        "#s": "Substance holonyms",
        "#p": "Part holonyms",
        "%m": "Member meronyms",
        "%s": "Substance meronyms",
        "%p": "Part meronyms",
        "=": "Attributes",
        "+": "Derivationally related forms",
        ";c": "Domain of synset - TOPIC",
        "-c": "Member of this domain - TOPIC",
        ";r": "Domain of synset - REGION",
        "-r": "Member of this domain - REGION",
        ";u": "Domain of synset - USAGE",
        "-u": "Member of this domain - USAGE",
    }

    v = {
        "!": "Antonyms",
        "@": "Hypernyms",
        "~": "Hyponyms",
        "*": "Entailments",
        ">": "Cause",
        "^": "Also see",
        "$": "Verb group",
        "+": "Derivationally related forms",
        ";c": "Domain of synset - TOPIC",
        ";r": "Domain of synset - REGION",
        ";u": "Domain of synset - USAGE",
    }

    a = s = {
        "!": "Antonyms",
        "+": "Derivationally related forms",
        "&": "Similar to",
        "<": "Participle of verb",
        "\\": "Pertainyms",
        "=": "Attributes",
        "^": "Also see",
        ";c": "Domain of synset - TOPIC",
        ";r": "Domain of synset - REGION",
        ";u": "Domain of synset - USAGE",
    }

    r = {
        "!": "Antonyms",
        "\\": "Derived from adjective",
        "+": "Derivationally related forms",
        ";c": "Domain of synset - TOPIC",
        ";r": "Domain of synset - REGION",
        ";u": "Domain of synset - USAGE",
    }


class Pointer(object):
    def __init__(self, symbol, offset, pos, source_target):
        self.symbol = symbol
        self.offset = int(offset)
        self.pos = pos
        self.source_target = source_target
        self.source = int(source_target[:2], 16)
        self.target = int(source_target[2:], 16)

    def __repr__(self):
        return "Pointer(%r, %r, %r, %r)" % (
            self.symbol,
            self.offset,
            self.pos,
            self.source_target,
        )


class WordNet(object):
    def __init__(self, wordnetdir, slb):
        self.wordnetdir = wordnetdir
        self.collector = defaultdict(list)
        self.slb = slb

    def prepare(self):

        ss_types = {
            "n": "n.",
            "v": "v.",
            "a": "adj.",
            "s": "adj. satellite",
            "r": "adv.",
        }

        file2pos = {
            "data.adj": ["a", "s"],
            "data.adv": ["r"],
            "data.noun": ["n"],
            "data.verb": ["v"],
        }

        dict_dir = os.path.join(self.wordnetdir, "dict")

        files = {}
        for name in os.listdir(dict_dir):
            if name.startswith("data."):
                if name in file2pos:
                    f = open(os.path.join(dict_dir, name), "r")
                    for key in file2pos[name]:
                        files[key] = f

        def a(word):
            return '<a href="%s">%s</a>' % (word, word)

        for i, line in enumerate(iterlines(self.wordnetdir)):
            if i % 100 == 0 and i > 0:
                sys.stdout.write(".")
                sys.stdout.flush()
            if i % 5000 == 0 and i > 0:
                sys.stdout.write("\n")
                sys.stdout.flush()
            if not line or not line.strip():
                continue
            synset = SynSet(line)
            gloss_with_examples, _ = quoted_text.subn(
                lambda x: '<cite class="ex">%s</cite>' % x.group(1), synset.gloss
            )
            gloss_with_examples, _ = ref.subn(
                lambda x: a(x.group(1)), gloss_with_examples
            )

            words = synset.words
            for i, word in enumerate(words):
                synonyms = [w for w in words if w != word]
                synonyms_str = (
                    '<br/><small class="co">Synonyms:</small> %s'
                    % ", ".join([a(w) for w in synonyms])
                    if synonyms
                    else ""
                )
                pointers = defaultdict(list)
                for pointer in synset.pointers:
                    if pointer.source and pointer.target and pointer.source - 1 != i:
                        continue
                    symbol = pointer.symbol
                    if symbol and symbol[:1] in (";", "-"):
                        continue
                    try:
                        symbol_desc = getattr(PointerSymbols, synset.ss_type)[symbol]
                    except KeyError:
                        print(
                            "WARNING: unknown pointer symbol %s for %s "
                            % (symbol, synset.ss_type)
                        )
                        symbol_desc = symbol

                    data_file = files[pointer.pos]
                    data_file.seek(pointer.offset)
                    referenced_synset = SynSet(data_file.readline())
                    if pointer.source == 0 and pointer.target == 0:
                        pointers[symbol_desc] = [
                            w for w in referenced_synset.words if w not in words
                        ]
                    else:
                        referenced_word = referenced_synset.words[pointer.target - 1]
                        if referenced_word not in pointers[symbol_desc]:
                            pointers[symbol_desc].append(referenced_word)

                pointers_str = ""
                for symbol_desc, referenced_words in pointers.items():
                    if referenced_words:
                        pointers_str += (
                            '<br/><small class="co">%s:</small> ' % symbol_desc
                        )
                        pointers_str += ", ".join([a(w) for w in referenced_words])
                self.collector[word].append(
                    '<i class="pos">%s</i> %s%s%s'
                    % (
                        ss_types[synset.ss_type],
                        gloss_with_examples,
                        synonyms_str,
                        pointers_str,
                    )
                )
        sys.stdout.write("\n")
        sys.stdout.flush()

    def process(self):

        article_template = (
            '<script src="~/js/styleswitcher.js"></script>'
            '<link rel="stylesheet" href="~/css/default.css" type="text/css">'
            '<link rel="alternate stylesheet" href="~/css/night.css" type="text/css" title="Night">'
            "<h1>%s</h1><span>%s</span>"
        )

        for title in self.collector:
            article_pieces = self.collector[title]
            article_pieces_count = len(article_pieces)
            text = None
            if article_pieces_count > 1:
                ol = (
                    ["<ol>"] + ["<li>%s</li>" % ap for ap in article_pieces] + ["</ol>"]
                )
                text = article_template % (title, "".join(ol))
            elif article_pieces_count == 1:
                text = article_template % (title, article_pieces[0])

            if text:
                self.slb.add(
                    text.encode("utf-8"), title, content_type="text/html;charset=utf-8"
                )

    def run(self):
        self.prepare()
        self.process()


def parse_args():

    arg_parser = argparse.ArgumentParser()

    arg_parser.add_argument(
        "-s",
        "--source-dir",
        type=str,
        default=".",
        help=(
            "Path to WordNet source directory "
            "(containing dict subdirectory). "
            "Default: %(default)s"
        ),
    )

    arg_parser.add_argument(
        "-o", "--output-file", type=str, help="Name of output slob file"
    )

    arg_parser.add_argument(
        "-c",
        "--compression",
        choices=["lzma2", "zlib"],
        default="zlib",
        help="Name of compression to use. Default: %(default)s",
    )

    arg_parser.add_argument(
        "-b",
        "--bin-size",
        type=int,
        default=384,
        help=("Minimum storage bin size in kilobytes. " "Default: %(default)s"),
    )

    arg_parser.add_argument(
        "-a",
        "--created-by",
        type=str,
        default="",
        help=(
            "Value for created.by tag. "
            "Identifier (e.g. name or email) "
            "for slob file creator"
        ),
    )

    arg_parser.add_argument(
        "-w",
        "--work-dir",
        type=str,
        default=".",
        help=(
            "Directory for temporary files "
            "created during compilation. "
            "Default: %(default)s"
        ),
    )

    return arg_parser.parse_args()


def main():

    observer = slob.SimpleTimingObserver()

    args = parse_args()

    outname = args.output_file
    if outname is None:
        outname = os.path.extsep.join(("wordnet", args.compression, "slob"))

    wordnetdir = os.path.expanduser(args.source_dir)

    if not os.path.exists(os.path.join(wordnetdir, "dict")):
        print(
            "%s doesn't contain dict subdirectory, "
            "doesn't look like WordNet source" % wordnetdir
        )
        raise SystemExit(1)

    with slob.create(
        outname,
        compression=args.compression,
        workdir=args.work_dir,
        min_bin_size=args.bin_size * 1024,
        observer=observer,
    ) as slb:
        observer.begin("all")
        observer.begin("content")
        # create tags
        slb.tag("label", "WordNet")
        slb.tag("license.name", "WordNet License")
        slb.tag("license.url", "http://wordnet.princeton.edu/wordnet/license/")
        slb.tag("source", "http://wordnet.princeton.edu")
        slb.tag("uri", "http://wordnet.princeton.edu")
        slb.tag("copyright", "2011 Princeton University")
        slb.tag("created.by", args.created_by)
        wordnet = WordNet(wordnetdir, slb)
        content_dir = os.path.dirname(__file__)
        slob.add_dir(slb, content_dir, include_only={"js", "css"}, prefix="~/")
        wordnet.run()

    print("\nAll done in %s\n" % observer.end("all"))
