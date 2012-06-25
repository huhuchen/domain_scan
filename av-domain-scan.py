# invRegex.py
#
# Copyright 2008, Paul McGuire
#
# pyparsing script to expand a regular expression into all possible matching strings
# Supports:
# - {n} and {m,n} repetition, but not unbounded + or * repetition
# - ? optional elements
# - [] character ranges
# - () grouping
# - | alternation
#
__all__ = ["count","invert"]

import sys, envoy, itertools

from pyparsing import (Literal, oneOf, printables, ParserElement, Combine, 
    SkipTo, operatorPrecedence, ParseFatalException, Word, nums, opAssoc,
    Suppress, ParseResults, srange)

class CharacterRangeEmitter(object):
    def __init__(self,chars):
        # remove duplicate chars in character range, but preserve original order
        seen = set()
        self.charset = "".join( seen.add(c) or c for c in chars if c not in seen )
    def __str__(self):
        return '['+self.charset+']'
    def __repr__(self):
        return '['+self.charset+']'
    def makeGenerator(self):
        def genChars():
            for s in self.charset:
                yield s
        return genChars

class OptionalEmitter(object):
    def __init__(self,expr):
        self.expr = expr
    def makeGenerator(self):
        def optionalGen():
            yield ""
            for s in self.expr.makeGenerator()():
                yield s
        return optionalGen

class DotEmitter(object):
    def makeGenerator(self):
        def dotGen():
            for c in printables:
                yield c
        return dotGen

class GroupEmitter(object):
    def __init__(self,exprs):
        self.exprs = ParseResults(exprs)
    def makeGenerator(self):
        def groupGen():
            def recurseList(elist):
                if len(elist)==1:
                    for s in elist[0].makeGenerator()():
                        yield s
                else:
                    for s in elist[0].makeGenerator()():
                        for s2 in recurseList(elist[1:]):
                            yield s + s2
            if self.exprs:
                for s in recurseList(self.exprs):
                    yield s
        return groupGen

class AlternativeEmitter(object):
    def __init__(self,exprs):
        self.exprs = exprs
    def makeGenerator(self):
        def altGen():
            for e in self.exprs:
                for s in e.makeGenerator()():
                    yield s
        return altGen
        
class LiteralEmitter(object):
    def __init__(self,lit):
        self.lit = lit
    def __str__(self):
        return "Lit:"+self.lit
    def __repr__(self):
        return "Lit:"+self.lit
    def makeGenerator(self):
        def litGen():
            yield self.lit
        return litGen

def handleRange(toks):
    return CharacterRangeEmitter(srange(toks[0]))
    
def handleRepetition(toks):
    toks=toks[0]
    if toks[1] in "*+":
        raise ParseFatalException("",0,"unbounded repetition operators not supported")
    if toks[1] == "?":
        return OptionalEmitter(toks[0])
    if "count" in toks:
        return GroupEmitter([toks[0]] * int(toks.count))
    if "minCount" in toks:
        mincount = int(toks.minCount)
        maxcount = int(toks.maxCount)
        optcount = maxcount - mincount
        if optcount:
            opt = OptionalEmitter(toks[0])
            for i in range(1,optcount):
                opt = OptionalEmitter(GroupEmitter([toks[0],opt]))
            return GroupEmitter([toks[0]] * mincount + [opt])
        else:
            return [toks[0]] * mincount
            
def handleLiteral(toks):
    lit = ""
    for t in toks:
        if t[0] == "\\":
            if t[1] == "t":
                lit += '\t'
            else:
                lit += t[1]
        else:
            lit += t
    return LiteralEmitter(lit)    

def handleMacro(toks):
    macroChar = toks[0][1]
    if macroChar == "d":
        return CharacterRangeEmitter("0123456789")
    elif macroChar == "w":
        return CharacterRangeEmitter(srange("[A-Za-z0-9_]"))
    elif macroChar == "s":
        return LiteralEmitter(" ")
    else:
        raise ParseFatalException("",0,"unsupported macro character (" + macroChar + ")")

def handleSequence(toks):
    return GroupEmitter(toks[0])

def handleDot():
    return CharacterRangeEmitter(printables)

def handleAlternative(toks):
    return AlternativeEmitter(toks[0])


_parser = None
def parser():
    global _parser
    if _parser is None:
        ParserElement.setDefaultWhitespaceChars("")
        lbrack,rbrack,lbrace,rbrace,lparen,rparen = map(Literal,"[]{}()")

        reMacro = Combine("\\" + oneOf(list("dws")))
        escapedChar = ~reMacro + Combine("\\" + oneOf(list(printables)))
        reLiteralChar = "".join(c for c in printables if c not in r"\[]{}().*?+|") + " \t"

        reRange = Combine(lbrack + SkipTo(rbrack,ignore=escapedChar) + rbrack)
        reLiteral = ( escapedChar | oneOf(list(reLiteralChar)) )
        reDot = Literal(".")
        repetition = (
            ( lbrace + Word(nums).setResultsName("count") + rbrace ) |
            ( lbrace + Word(nums).setResultsName("minCount")+","+ Word(nums).setResultsName("maxCount") + rbrace ) |
            oneOf(list("*+?")) 
            )

        reRange.setParseAction(handleRange)
        reLiteral.setParseAction(handleLiteral)
        reMacro.setParseAction(handleMacro)
        reDot.setParseAction(handleDot)
        
        reTerm = ( reLiteral | reRange | reMacro | reDot )
        reExpr = operatorPrecedence( reTerm,
            [
            (repetition, 1, opAssoc.LEFT, handleRepetition),
            (None, 2, opAssoc.LEFT, handleSequence),
            (Suppress('|'), 2, opAssoc.LEFT, handleAlternative),
            ]
            )
        _parser = reExpr
        
    return _parser

def count(gen):
    """Simple function to count the number of elements returned by a generator."""
    i = 0
    for s in gen:
        i += 1
    return i

def invert(regex):
    """Call this routine as a generator to return all the strings that
       match the input regular expression.
           for s in invert("[A-Z]{3}\d{3}"):
               print s
    """
    invReGenerator = GroupEmitter(parser().parseString(regex)).makeGenerator()
    return invReGenerator()

def generate_domain(input_str):
    domain = []
    if '?' in input_str:
        result = []
        count = input_str.count('?')
        all_str = negex_str()
        all_combinations = itertools.product(all_str, repeat=count) 
        initial_domain = [list(input_str)] * (len(all_str) ** count)
        for item in initial_domain:
            result.append(replace_wildcard(item, all_combinations.next()))
        return [''.join(item) for item in result]
    domain.append(input_str)
    return domain

def replace_wildcard(_string, value):
    result = _string[:]
    value = (item for item in value)
    for key, _value in enumerate(result):
        if '?' == _value:
            result[key] = value.next()
    return result



def main(input_str):
    print generate_domain(input_str)

def negex_str():
    negex = r'[0-9a-zA-Z]'
    result = []
    for s in invert(negex):
        result.append(s)
    return ''.join(result)    

if __name__ == "__main__":
    input_str = sys.argv[1]
    main(input_str)
