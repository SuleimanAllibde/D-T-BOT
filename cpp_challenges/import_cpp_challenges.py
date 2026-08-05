# -*- coding: utf-8 -*-
"""
Import the C++ challenge bank (cpp_challenges/*/*.sql) into the challenges
database. Each challenge gets:
  - a C++ starter template
  - a visible example (input/output/explanation)
  - one or more VISIBLE test cases (hidden=0) so the guessed I/O format can be
    inspected and corrected from the dashboard / solve result messages.
Run:  python cpp_challenges/import_cpp_challenges.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_session, ChallengeSetting, Challenge, \
    ChallengeStarterCode, ChallengeExample, ChallengeTestCase
from config import GUILD_ID

CXX_STARTER = """#include <bits/stdc++.h>
using namespace std;

int main() {
    
}
"""

# key -> dict(title, cat, diff, xp, coins, time_limit, est, inp, out, expl)
# desc is generated from inp/out/expl.
SPECS = {
    # ============ EASY ============
    "CPP-001": dict(title="Sum of Two Numbers", cat="Basics", diff="Easy", xp=21, coins=5, time_limit=2, est="~5 min",
                    inp="3 5", out="8", expl="3 + 5 = 8"),
    "CPP-002": dict(title="Maximum of Three Numbers", cat="Conditions", diff="Easy", xp=22, coins=5, time_limit=2, est="~5 min",
                    inp="3 5 1", out="5", expl="5 is the largest"),
    "CPP-003": dict(title="Even or Odd", cat="Math", diff="Easy", xp=23, coins=5, time_limit=2, est="~5 min",
                    inp="7", out="Odd", expl="7 is not divisible by 2"),
    "CPP-004": dict(title="Reverse a String", cat="Strings", diff="Easy", xp=24, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="olleh", expl="Reversed"),
    "CPP-005": dict(title="Count Vowels", cat="Strings", diff="Easy", xp=25, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="2", expl="e and o are vowels"),
    "CPP-006": dict(title="Factorial", cat="Math", diff="Easy", xp=26, coins=5, time_limit=2, est="~5 min",
                    inp="5", out="120", expl="5! = 5*4*3*2*1"),
    "CPP-007": dict(title="Prime Number Check", cat="Math", diff="Easy", xp=27, coins=5, time_limit=2, est="~5 min",
                    inp="7", out="Prime", expl="7 has no divisors other than 1 and itself",
                    extra=[("10", "Composite", "10 = 2*5")]),
    "CPP-008": dict(title="Find Maximum in Array", cat="Arrays", diff="Easy", xp=28, coins=5, time_limit=2, est="~5 min",
                    inp="5\n3 7 2 9 1", out="9", expl="9 is the largest value"),
    "CPP-009": dict(title="Average of Numbers", cat="Arrays", diff="Easy", xp=29, coins=5, time_limit=2, est="~5 min",
                    inp="4\n2 4 6 8", out="5", expl="(2+4+6+8)/4 = 5"),
    "CPP-010": dict(title="Palindrome Check", cat="Strings", diff="Easy", xp=30, coins=5, time_limit=2, est="~5 min",
                    inp="madam", out="Yes", expl="reads the same backwards",
                    extra=[("hello", "No", "not a palindrome")]),
    "CPP-011": dict(title="Count Digits", cat="Math", diff="Easy", xp=31, coins=5, time_limit=2, est="~5 min",
                    inp="12345", out="5", expl="5 digits"),
    "CPP-012": dict(title="Swap Two Numbers", cat="Basics", diff="Easy", xp=32, coins=5, time_limit=2, est="~5 min",
                    inp="5 3", out="3 5", expl="swap the two numbers"),
    "CPP-013": dict(title="Smallest Number", cat="Conditions", diff="Easy", xp=33, coins=5, time_limit=2, est="~5 min",
                    inp="5 2 8", out="2", expl="2 is the smallest"),
    "CPP-014": dict(title="Count Words", cat="Strings", diff="Easy", xp=34, coins=5, time_limit=2, est="~5 min",
                    inp="hello world foo", out="3", expl="three space-separated words"),
    "CPP-015": dict(title="Sum of Array", cat="Arrays", diff="Easy", xp=35, coins=5, time_limit=2, est="~5 min",
                    inp="4\n1 2 3 4", out="10", expl="1+2+3+4 = 10"),
    "CPP-016": dict(title="Find Minimum in Array", cat="Arrays", diff="Easy", xp=36, coins=5, time_limit=2, est="~5 min",
                    inp="5\n3 7 2 9 1", out="1", expl="1 is the smallest value"),
    "CPP-017": dict(title="Capitalize Letters", cat="Strings", diff="Easy", xp=37, coins=5, time_limit=2, est="~5 min",
                    inp="hello world", out="Hello World", expl="each word starts with a capital"),
    "CPP-018": dict(title="Multiplication Table", cat="Loops", diff="Easy", xp=38, coins=5, time_limit=2, est="~5 min",
                    inp="3", out="3 x 1 = 3\n3 x 2 = 6\n3 x 3 = 9\n3 x 4 = 12\n3 x 5 = 15\n3 x 6 = 18\n3 x 7 = 21\n3 x 8 = 24\n3 x 9 = 27\n3 x 10 = 30",
                    expl="table of 3 from 1 to 10"),
    "CPP-019": dict(title="Fibonacci Number", cat="Math", diff="Easy", xp=39, coins=5, time_limit=2, est="~5 min",
                    inp="7", out="13", expl="fib(0)=0, fib(1)=1 ... fib(7)=13"),
    "CPP-020": dict(title="Count Even Numbers", cat="Arrays", diff="Easy", xp=40, coins=5, time_limit=2, est="~5 min",
                    inp="6\n1 2 3 4 5 6", out="3", expl="2,4,6 are even"),
    "CPP-021": dict(title="Second Largest Number", cat="Arrays", diff="Easy", xp=41, coins=5, time_limit=2, est="~5 min",
                    inp="5\n3 7 2 9 1", out="7", expl="9 is largest, 7 is second"),
    "CPP-022": dict(title="Count Positive Numbers", cat="Arrays", diff="Easy", xp=42, coins=5, time_limit=2, est="~5 min",
                    inp="5\n-1 2 0 5 -3", out="2", expl="2 and 5 are positive"),
    "CPP-023": dict(title="Remove Spaces", cat="Strings", diff="Easy", xp=43, coins=5, time_limit=2, est="~5 min",
                    inp="a b c", out="abc", expl="spaces removed"),
    "CPP-024": dict(title="String Length Without size()", cat="Strings", diff="Easy", xp=44, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="5", expl="5 characters"),
    "CPP-025": dict(title="Convert to Uppercase", cat="Strings", diff="Easy", xp=45, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="HELLO", expl="all letters uppercase"),
    "CPP-026": dict(title="Linear Search", cat="Searching", diff="Easy", xp=46, coins=5, time_limit=2, est="~5 min",
                    inp="5\n3 7 2 9 1\n9", out="4", expl="9 is at 1-based position 4",
                    extra=[("4\n1 2 3 4\n8", "-1", "8 not found")]),
    "CPP-027": dict(title="Count Characters", cat="Strings", diff="Easy", xp=47, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="5", expl="5 characters"),
    "CPP-028": dict(title="Simple Calculator", cat="Basics", diff="Easy", xp=48, coins=5, time_limit=2, est="~5 min",
                    inp="5 3 +", out="8", expl="5 + 3 = 8"),
    "CPP-029": dict(title="Power of Number", cat="Math", diff="Easy", xp=49, coins=5, time_limit=2, est="~5 min",
                    inp="2 10", out="1024", expl="2^10 = 1024"),
    "CPP-030": dict(title="Print Star Pyramid", cat="Loops", diff="Easy", xp=50, coins=5, time_limit=2, est="~5 min",
                    inp="4", out="*\n**\n***\n****", expl="left-aligned pyramid of height 4"),
    "CPP-031": dict(title="Count Odd Numbers", cat="Arrays", diff="Easy", xp=51, coins=5, time_limit=2, est="~5 min",
                    inp="6\n1 2 3 4 5 6", out="3", expl="1,3,5 are odd"),
    "CPP-032": dict(title="Reverse Array", cat="Arrays", diff="Easy", xp=52, coins=5, time_limit=2, est="~5 min",
                    inp="5\n1 2 3 4 5", out="5 4 3 2 1", expl="array reversed"),
    "CPP-033": dict(title="Find Minimum and Maximum", cat="Arrays", diff="Easy", xp=53, coins=5, time_limit=2, est="~5 min",
                    inp="5\n3 7 2 9 1", out="1 9", expl="min then max"),
    "CPP-034": dict(title="Count Uppercase Letters", cat="Strings", diff="Easy", xp=54, coins=5, time_limit=2, est="~5 min",
                    inp="HeLLo", out="3", expl="H, L, L are uppercase"),
    "CPP-035": dict(title="Count Lowercase Letters", cat="Strings", diff="Easy", xp=55, coins=5, time_limit=2, est="~5 min",
                    inp="HeLLo", out="2", expl="e, o are lowercase"),
    "CPP-036": dict(title="ASCII Value", cat="Basics", diff="Easy", xp=56, coins=5, time_limit=2, est="~5 min",
                    inp="A", out="65", expl="ASCII of A is 65"),
    "CPP-037": dict(title="Leap Year Checker", cat="Conditions", diff="Easy", xp=57, coins=5, time_limit=2, est="~5 min",
                    inp="2024", out="Leap", expl="2024 is divisible by 4 and not by 100",
                    extra=[("2023", "Not Leap", "not divisible by 4")]),
    "CPP-038": dict(title="Greatest Common Divisor", cat="Math", diff="Easy", xp=58, coins=5, time_limit=2, est="~5 min",
                    inp="12 18", out="6", expl="gcd(12,18)=6"),
    "CPP-039": dict(title="Least Common Multiple", cat="Math", diff="Easy", xp=59, coins=5, time_limit=2, est="~5 min",
                    inp="4 6", out="12", expl="lcm(4,6)=12"),
    "CPP-040": dict(title="Remove Duplicate Characters", cat="Strings", diff="Easy", xp=60, coins=5, time_limit=2, est="~5 min",
                    inp="hello", out="helo", expl="keep first occurrence"),
    "CPP-041": dict(title="Binary to Decimal", cat="Math", diff="Easy", xp=61, coins=5, time_limit=2, est="~5 min",
                    inp="1010", out="10", expl="binary 1010 = 10"),
    "CPP-042": dict(title="Decimal to Binary", cat="Math", diff="Easy", xp=62, coins=5, time_limit=2, est="~5 min",
                    inp="10", out="1010", expl="10 in binary is 1010"),
    "CPP-043": dict(title="Count Digits Frequency", cat="Math", diff="Easy", xp=63, coins=5, time_limit=2, est="~5 min",
                    inp="112233 2", out="3", expl="digit 2 appears 3 times"),
    "CPP-044": dict(title="Find Missing Number", cat="Arrays", diff="Easy", xp=64, coins=5, time_limit=2, est="~5 min",
                    inp="5\n1 2 3 5", out="4", expl="4 is missing from 1..5"),
    "CPP-045": dict(title="Merge Two Arrays", cat="Arrays", diff="Easy", xp=65, coins=5, time_limit=2, est="~5 min",
                    inp="3\n1 3 5\n3\n2 4 6", out="1 2 3 4 5 6", expl="merged and sorted"),
    "CPP-046": dict(title="Rotate Array Left", cat="Arrays", diff="Easy", xp=66, coins=5, time_limit=2, est="~5 min",
                    inp="5\n1 2 3 4 5\n2", out="3 4 5 1 2", expl="rotated left by 2"),
    "CPP-047": dict(title="Count Words in Sentence", cat="Strings", diff="Easy", xp=67, coins=5, time_limit=2, est="~5 min",
                    inp="hello world foo", out="3", expl="three words"),
    "CPP-048": dict(title="Anagram Check", cat="Strings", diff="Easy", xp=68, coins=5, time_limit=2, est="~5 min",
                    inp="listen silent", out="Yes", expl="same letters rearranged",
                    extra=[("hello world", "No", "not anagrams")]),
    "CPP-049": dict(title="Sort Three Numbers", cat="Sorting", diff="Easy", xp=69, coins=5, time_limit=2, est="~5 min",
                    inp="3 1 2", out="1 2 3", expl="sorted ascending"),
    "CPP-050": dict(title="Unique Elements", cat="Arrays", diff="Easy", xp=70, coins=5, time_limit=2, est="~5 min",
                    inp="6\n1 2 2 3 3 3", out="1 2 3", expl="first-occurrence order"),

    # ============ MEDIUM ============
    "CPP-051": dict(title="Binary Search", cat="Searching", diff="Medium", xp=80, coins=10, time_limit=2, est="~10 min",
                    inp="6\n1 3 5 7 9 11\n7", out="4", expl="7 is at 1-based position 4",
                    extra=[("5\n1 2 3 4 5\n9", "-1", "9 not found")]),
    "CPP-052": dict(title="Selection Sort", cat="Sorting", diff="Medium", xp=81, coins=10, time_limit=2, est="~10 min",
                    inp="6\n5 3 8 1 9 2", out="1 2 3 5 8 9", expl="sorted ascending"),
    "CPP-053": dict(title="Bubble Sort", cat="Sorting", diff="Medium", xp=82, coins=10, time_limit=2, est="~10 min",
                    inp="6\n5 3 8 1 9 2", out="1 2 3 5 8 9", expl="sorted ascending"),
    "CPP-054": dict(title="Insertion Sort", cat="Sorting", diff="Medium", xp=83, coins=10, time_limit=2, est="~10 min",
                    inp="6\n5 3 8 1 9 2", out="1 2 3 5 8 9", expl="sorted ascending"),
    "CPP-055": dict(title="Merge Two Sorted Arrays", cat="Arrays", diff="Medium", xp=84, coins=10, time_limit=2, est="~10 min",
                    inp="4\n1 3 5 7\n3\n2 4 6", out="1 2 3 4 5 6 7", expl="merged sorted"),
    "CPP-056": dict(title="Matrix Addition", cat="Matrices", diff="Medium", xp=85, coins=10, time_limit=2, est="~10 min",
                    inp="2 2\n1 2\n3 4\n5 6\n7 8", out="6 8\n10 12", expl="element-wise sum"),
    "CPP-057": dict(title="Matrix Transpose", cat="Matrices", diff="Medium", xp=86, coins=10, time_limit=2, est="~10 min",
                    inp="2 3\n1 2 3\n4 5 6", out="1 4\n2 5\n3 6", expl="rows become columns"),
    "CPP-058": dict(title="Check Palindrome Number", cat="Math", diff="Medium", xp=87, coins=10, time_limit=2, est="~10 min",
                    inp="121", out="Yes", expl="reads the same reversed",
                    extra=[("123", "No", "reversed is 321")]),
    "CPP-059": dict(title="Longest Word", cat="Strings", diff="Medium", xp=88, coins=10, time_limit=2, est="~10 min",
                    inp="hello world programming", out="programming", expl="longest word"),
    "CPP-060": dict(title="Remove Duplicate Array Values", cat="Arrays", diff="Medium", xp=89, coins=10, time_limit=2, est="~10 min",
                    inp="7\n1 2 2 3 4 4 5", out="1 2 3 4 5", expl="duplicates removed"),
    "CPP-061": dict(title="Rotate Matrix 90 Degrees", cat="Matrices", diff="Medium", xp=90, coins=10, time_limit=2, est="~10 min",
                    inp="2 2\n1 2\n3 4", out="3 1\n4 2", expl="clockwise rotation"),
    "CPP-062": dict(title="Two Sum", cat="Arrays", diff="Medium", xp=91, coins=10, time_limit=2, est="~10 min",
                    inp="5\n2 7 11 15\n9", out="0 1", expl="2 + 7 = 9 (0-based indices)"),
    "CPP-063": dict(title="Valid Parentheses", cat="Stacks", diff="Medium", xp=92, coins=10, time_limit=2, est="~10 min",
                    inp="({[]})", out="Yes", expl="balanced brackets",
                    extra=[("([)]", "No", "mismatched order")]),
    "CPP-064": dict(title="Prefix Sum Queries", cat="Arrays", diff="Medium", xp=93, coins=10, time_limit=2, est="~10 min",
                    inp="5\n1 2 3 4 5\n2\n1 3\n2 5", out="6\n14", expl="range sums (1-based inclusive)"),
    "CPP-065": dict(title="Count Distinct Elements", cat="Hashing", diff="Medium", xp=94, coins=10, time_limit=2, est="~10 min",
                    inp="6\n1 2 2 3 4 3", out="4", expl="{1,2,3,4}"),
    "CPP-066": dict(title="Frequency Map", cat="Hashing", diff="Medium", xp=95, coins=10, time_limit=2, est="~10 min",
                    inp="5\n1 1 2 3 3", out="1:2 2:1 3:2", expl="value:count in first-appearance order"),
    "CPP-067": dict(title="Merge Intervals", cat="Intervals", diff="Medium", xp=96, coins=10, time_limit=2, est="~10 min",
                    inp="3\n1 3\n2 6\n8 10", out="1 6\n8 10", expl="overlapping intervals merged"),
    "CPP-068": dict(title="Kadane Maximum Subarray", cat="Arrays", diff="Medium", xp=97, coins=10, time_limit=2, est="~10 min",
                    inp="8\n-2 1 -3 4 -1 2 1 -5", out="6", expl="max subarray sum is 6 (4,-1,2,1)"),
    "CPP-069": dict(title="Move Zeroes", cat="Arrays", diff="Medium", xp=98, coins=10, time_limit=2, est="~10 min",
                    inp="6\n0 1 0 3 12 0", out="1 3 12 0 0 0", expl="non-zero first, then zeroes"),
    "CPP-070": dict(title="Longest Common Prefix", cat="Strings", diff="Medium", xp=99, coins=10, time_limit=2, est="~10 min",
                    inp="3\nflower\nflow\nflight", out="fl", expl="common prefix"),
    "CPP-071": dict(title="Group Anagrams", cat="Hashing", diff="Medium", xp=100, coins=10, time_limit=2, est="~10 min",
                    inp="4\nlisten\nsilent\nenlist\nabc", out="2", expl="two anagram groups"),
    "CPP-072": dict(title="Product of Array Except Self", cat="Arrays", diff="Medium", xp=101, coins=10, time_limit=2, est="~10 min",
                    inp="4\n1 2 3 4", out="24 12 8 6", expl="product of all other elements"),
    "CPP-073": dict(title="Spiral Matrix", cat="Matrices", diff="Medium", xp=102, coins=10, time_limit=2, est="~10 min",
                    inp="3 3\n1 2 3\n4 5 6\n7 8 9", out="1 2 3 6 9 8 7 4 5", expl="spiral order"),
    "CPP-074": dict(title="Rotate String", cat="Strings", diff="Medium", xp=103, coins=10, time_limit=2, est="~10 min",
                    inp="abcde cdeab", out="Yes", expl="cdeab is abcde rotated",
                    extra=[("abcde abced", "No", "not a rotation")]),
    "CPP-075": dict(title="Longest Palindromic Prefix", cat="Strings", diff="Medium", xp=104, coins=10, time_limit=2, est="~10 min",
                    inp="abacaba", out="aba", expl="longest palindromic prefix"),
    "CPP-076": dict(title="Intersection of Two Arrays", cat="Arrays", diff="Medium", xp=105, coins=10, time_limit=2, est="~10 min",
                    inp="4\n1 2 2 1\n2\n2 2", out="2", expl="unique common value is 2"),
    "CPP-077": dict(title="Majority Element", cat="Arrays", diff="Medium", xp=106, coins=10, time_limit=2, est="~10 min",
                    inp="5\n3 3 4 2 3", out="3", expl="appears > n/2 times"),
    "CPP-078": dict(title="Top K Frequent Elements", cat="Hashing", diff="Medium", xp=107, coins=10, time_limit=2, est="~10 min",
                    inp="6\n1 1 1 2 2 3\n2", out="1 2", expl="two most frequent"),
    "CPP-079": dict(title="Evaluate Postfix Expression", cat="Stacks", diff="Medium", xp=108, coins=10, time_limit=2, est="~10 min",
                    inp="3 4 + 2 *", out="14", expl="(3+4)*2 = 14"),
    "CPP-080": dict(title="Balanced Brackets", cat="Stacks", diff="Medium", xp=109, coins=10, time_limit=2, est="~10 min",
                    inp="{[()]}", out="Yes", expl="balanced",
                    extra=[("{[(])}", "No", "unbalanced")]),
    "CPP-081": dict(title="Sliding Window Maximum", cat="Queues", diff="Medium", xp=110, coins=10, time_limit=2, est="~10 min",
                    inp="8\n1 3 -1 -3 5 3 6 7\n3", out="3 3 5 5 6 7", expl="max in each window of size 3"),
    "CPP-082": dict(title="Longest Substring Without Repeating", cat="Strings", diff="Medium", xp=111, coins=10, time_limit=2, est="~10 min",
                    inp="abcabcbb", out="3", expl="abc has length 3"),
    "CPP-083": dict(title="Binary Search on Answer", cat="Searching", diff="Medium", xp=112, coins=10, time_limit=2, est="~10 min",
                    inp="6\n1 2 3 4 5 6\n4", out="3", expl="count of elements < 4"),
    "CPP-084": dict(title="Merge K Sorted Arrays", cat="Heap", diff="Medium", xp=113, coins=10, time_limit=2, est="~10 min",
                    inp="3\n2\n1 4\n2\n2 5\n2\n3 6", out="1 2 3 4 5 6", expl="all merged sorted"),
    "CPP-085": dict(title="Next Greater Element", cat="Stacks", diff="Medium", xp=114, coins=10, time_limit=2, est="~10 min",
                    inp="4\n4 5 2 25", out="5 25 25 -1", expl="next greater for each"),
    "CPP-086": dict(title="Monotonic Stack Basics", cat="Stacks", diff="Medium", xp=115, coins=10, time_limit=2, est="~10 min",
                    inp="4\n4 5 2 10", out="2 2 -1 -1", expl="next smaller for each"),
    "CPP-087": dict(title="Subarray Sum Equals K", cat="Prefix Sum", diff="Medium", xp=116, coins=10, time_limit=2, est="~10 min",
                    inp="3\n1 1 1\n2", out="2", expl="two subarrays sum to 2"),
    "CPP-088": dict(title="Minimum Window Substring", cat="Strings", diff="Medium", xp=117, coins=10, time_limit=2, est="~10 min",
                    inp="ADOBECODEBANC ABC", out="BANC", expl="minimum window containing A,B,C"),
    "CPP-089": dict(title="Longest Consecutive Sequence", cat="Hashing", diff="Medium", xp=118, coins=10, time_limit=2, est="~10 min",
                    inp="6\n100 4 200 1 3 2", out="4", expl="1,2,3,4"),
    "CPP-090": dict(title="Search in Rotated Sorted Array", cat="Searching", diff="Medium", xp=119, coins=10, time_limit=2, est="~10 min",
                    inp="7\n4 5 6 7 0 1 2\n0", out="5", expl="0 at 1-based position 5",
                    extra=[("7\n4 5 6 7 0 1 2\n3", "-1", "3 not present")]),
    "CPP-091": dict(title="Trie Basics", cat="Trie", diff="Medium", xp=120, coins=10, time_limit=2, est="~10 min",
                    inp="3\nhello\nhelp\nheap\n2\nhel\nhea", out="2\n1", expl="words starting with each prefix"),
    "CPP-092": dict(title="Implement Min Heap", cat="Heap", diff="Medium", xp=121, coins=10, time_limit=2, est="~10 min",
                    inp="push 5\npush 3\nmin\npop\nmin", out="3\n3", expl="min after pushes, min after pop"),
    "CPP-093": dict(title="Kth Largest Element", cat="Heap", diff="Medium", xp=122, coins=10, time_limit=2, est="~10 min",
                    inp="6\n3 2 1 5 6 4\n2", out="5", expl="second largest is 5"),
    "CPP-094": dict(title="Detect Cycle in Linked List", cat="Linked Lists", diff="Medium", xp=123, coins=10, time_limit=2, est="~10 min",
                    inp="3\n1 2 3\n1", out="Yes", expl="cycle starts at index 1",
                    extra=[("3\n1 2 3\n-1", "No", "no cycle")]),
    "CPP-095": dict(title="Reverse Linked List", cat="Linked Lists", diff="Medium", xp=124, coins=10, time_limit=2, est="~10 min",
                    inp="5\n1 2 3 4 5", out="5 4 3 2 1", expl="list reversed"),
    "CPP-096": dict(title="Binary Tree Level Order Traversal", cat="Trees", diff="Medium", xp=125, coins=10, time_limit=2, est="~10 min",
                    inp="7\n1 2 3 -1 5 -1 7", out="1 2 3 5 7", expl="level order, -1 = missing, nulls skipped"),
    "CPP-097": dict(title="Lowest Common Ancestor", cat="Trees", diff="Medium", xp=126, coins=10, time_limit=2, est="~10 min",
                    inp="7\n6 2 8 0 4 7 9\n2 8", out="6", expl="BST, LCA of 2 and 8 is 6"),
    "CPP-098": dict(title="Flood Fill", cat="Graphs", diff="Medium", xp=127, coins=10, time_limit=2, est="~10 min",
                    inp="3 3\n1 1 1\n1 1 0\n1 0 1\n1 1", out="5", expl="connected region of 1s at (1,1) has 5 cells"),
    "CPP-099": dict(title="Number of Islands", cat="Graphs", diff="Medium", xp=128, coins=10, time_limit=2, est="~10 min",
                    inp="4 5\n11000\n11000\n00100\n00011", out="3", expl="three islands"),
    "CPP-100": dict(title="Dijkstra Shortest Path", cat="Graphs", diff="Medium", xp=129, coins=10, time_limit=2, est="~10 min",
                    inp="4 5\n0 1 1\n1 2 2\n0 2 4\n2 3 1\n1 3 5\n0 3", out="4", expl="shortest path 0->3 is 0-1-2-3 = 4"),

    # ============ HARD ============
    "CPP-101": dict(title="Disjoint Set Union", cat="Graphs", diff="Hard", xp=200, coins=20, time_limit=3, est="~30 min",
                    inp="5\nunion 1 2\nunion 2 3\nfind 1 3\nfind 1 4", out="Yes\nNo", expl="1,2,3 connected; 4 not"),
    "CPP-102": dict(title="Topological Sort", cat="Graphs", diff="Hard", xp=201, coins=20, time_limit=3, est="~30 min",
                    inp="4 3\n0 1\n0 2\n1 3", out="0 1 2 3", expl="a valid topological order"),
    "CPP-103": dict(title="Kruskal Minimum Spanning Tree", cat="Graphs", diff="Hard", xp=202, coins=20, time_limit=3, est="~30 min",
                    inp="4 5\n0 1 10\n0 2 6\n0 3 5\n1 3 15\n2 3 4", out="21", expl="MST weight = 5+6+10"),
    "CPP-104": dict(title="Prim Minimum Spanning Tree", cat="Graphs", diff="Hard", xp=203, coins=20, time_limit=3, est="~30 min",
                    inp="4 5\n0 1 10\n0 2 6\n0 3 5\n1 3 15\n2 3 4", out="21", expl="MST weight = 5+6+10"),
    "CPP-105": dict(title="Bellman-Ford Algorithm", cat="Graphs", diff="Hard", xp=204, coins=20, time_limit=3, est="~30 min",
                    inp="3 3\n0 1 4\n1 2 3\n0 2 6\n0 2", out="6", expl="shortest 0->2 = min(6, 4+3) = 6"),
    "CPP-106": dict(title="Floyd-Warshall Algorithm", cat="Graphs", diff="Hard", xp=205, coins=20, time_limit=3, est="~30 min",
                    inp="3 3\n0 1 4\n1 2 3\n0 2 6", out="0 4 7\nINF 0 3\nINF INF 0", expl="all-pairs shortest matrix"),
    "CPP-107": dict(title="Segment Tree Range Sum", cat="Segment Tree", diff="Hard", xp=206, coins=20, time_limit=3, est="~30 min",
                    inp="6\n1 3 5 7 9 11\n3\nsum 0 2\nsum 1 4\nupdate 1 10\nsum 1 1", out="9\n24\n10", expl="range sums + point update"),
    "CPP-108": dict(title="Lazy Propagation", cat="Segment Tree", diff="Hard", xp=207, coins=20, time_limit=3, est="~30 min",
                    inp="5\n1 2 3 4 5\n3\nadd 1 3 2\nsum 0 4\nsum 1 2", out="21\n9", expl="range add then range sums"),
    "CPP-109": dict(title="Binary Lifting LCA", cat="Trees", diff="Hard", xp=208, coins=20, time_limit=3, est="~30 min",
                    inp="5\n0 1\n0 2\n1 3\n1 4\n2\n3 4\n2 4", out="1\n0", expl="LCA of queries"),
    "CPP-110": dict(title="Tree Diameter", cat="Trees", diff="Hard", xp=209, coins=20, time_limit=3, est="~30 min",
                    inp="5\n0 1\n0 2\n1 3\n1 4", out="3", expl="longest path length (edges)"),
    "CPP-111": dict(title="Heavy-Light Decomposition", cat="Trees", diff="Hard", xp=210, coins=20, time_limit=3, est="~30 min",
                    inp="4\n1 2 3 4\n0 1\n1 2\n1 3\n2\npath_sum 0 3\npath_sum 2 3", out="7\n9", expl="node values and path sums"),
    "CPP-112": dict(title="Centroid Decomposition", cat="Trees", diff="Hard", xp=211, coins=20, time_limit=3, est="~30 min",
                    inp="4\n0 1\n0 2\n1 3\ncount_distance 0 1", out="2", expl="pairs at distance 1 from node 0"),
    "CPP-113": dict(title="Strongly Connected Components", cat="Graphs", diff="Hard", xp=212, coins=20, time_limit=3, est="~30 min",
                    inp="4 4\n0 1\n1 2\n2 0\n2 3", out="2", expl="SCCs: {0,1,2} and {3}"),
    "CPP-114": dict(title="Tarjan Bridges", cat="Graphs", diff="Hard", xp=213, coins=20, time_limit=3, est="~30 min",
                    inp="4 3\n0 1\n1 2\n2 3", out="3", expl="all edges are bridges"),
    "CPP-115": dict(title="Tarjan Articulation Points", cat="Graphs", diff="Hard", xp=214, coins=20, time_limit=3, est="~30 min",
                    inp="5 5\n0 1\n0 2\n1 2\n1 3\n3 4", out="1", expl="node 1 is the articulation point"),
    "CPP-116": dict(title="Maximum Bipartite Matching", cat="Graphs", diff="Hard", xp=215, coins=20, time_limit=3, est="~30 min",
                    inp="2 2\n1\n0 1\n0\n0", out="1", expl="maximum matching size is 1"),
    "CPP-117": dict(title="Dinic Maximum Flow", cat="Graphs", diff="Hard", xp=216, coins=20, time_limit=3, est="~30 min",
                    inp="4 4 0 3\n0 1 10\n1 3 10\n0 2 5\n2 3 5", out="15", expl="max flow 0->3 = 15"),
    "CPP-118": dict(title="Convex Hull", cat="Geometry", diff="Hard", xp=217, coins=20, time_limit=3, est="~30 min",
                    inp="6\n0 0\n1 1\n2 2\n0 2\n2 0\n1 0", out="0 0\n0 2\n2 2\n2 0", expl="hull vertices in order"),
    "CPP-119": dict(title="Line Sweep Intersections", cat="Geometry", diff="Hard", xp=218, coins=20, time_limit=3, est="~30 min",
                    inp="2\n0 0 2 2\n0 2 2 0", out="1", expl="the two segments intersect"),
    "CPP-120": dict(title="Sparse Table RMQ", cat="Range Queries", diff="Hard", xp=219, coins=20, time_limit=3, est="~30 min",
                    inp="6\n2 5 3 1 8 4\n3\nmin 1 3\nmin 0 5\nmin 3 5", out="1\n1\n1", expl="range minimum queries (1-based)"),
    "CPP-121": dict(title="Suffix Array Construction", cat="Strings", diff="Hard", xp=220, coins=20, time_limit=3, est="~30 min",
                    inp="banana", out="5 3 1 0 4 2", expl="suffix array (0-based indices)"),
    "CPP-122": dict(title="Longest Common Substring", cat="Dynamic Programming", diff="Hard", xp=221, coins=20, time_limit=3, est="~30 min",
                    inp="abcdef abcxydef", out="3", expl="def length 3"),
    "CPP-123": dict(title="Aho-Corasick Automaton", cat="Strings", diff="Hard", xp=222, coins=20, time_limit=3, est="~30 min",
                    inp="ushers\nhe she his hers", out="3", expl="patterns found in text (unique matches)"),
    "CPP-124": dict(title="Knuth Optimization", cat="Dynamic Programming", diff="Hard", xp=223, coins=20, time_limit=3, est="~30 min",
                    inp="4\n3 1 2 5", out="13", expl="optimal merge cost"),
    "CPP-125": dict(title="Divide and Conquer DP", cat="Dynamic Programming", diff="Hard", xp=224, coins=20, time_limit=3, est="~30 min",
                    inp="4 2\n1 2 3 4", out="8", expl="minimum cost to split into 2 segments"),
    "CPP-126": dict(title="Bitmask Traveling Salesman", cat="Bitmask DP", diff="Hard", xp=225, coins=20, time_limit=3, est="~30 min",
                    inp="3\n0 10 15\n10 0 20\n15 20 0", out="45", expl="shortest tour 0->1->2->0 = 10+20+15"),
    "CPP-127": dict(title="Euler Tour Technique", cat="Trees", diff="Hard", xp=226, coins=20, time_limit=3, est="~30 min",
                    inp="4\n1 2 3 4\n0 1\n0 2\n1 3\n2\nsubtree_sum 1\nsubtree_sum 0", out="5\n10", expl="subtree sums"),
    "CPP-128": dict(title="Persistent Segment Tree", cat="Segment Tree", diff="Hard", xp=227, coins=20, time_limit=3, est="~30 min",
                    inp="5\n1 3 5 7 9\n3\nversion 0\nsum 0 4\nversion 1\nupdate 2 8\nsum 0 4", out="25\n24", expl="query across versions"),
    "CPP-129": dict(title="Mo's Algorithm", cat="Range Queries", diff="Hard", xp=229, coins=20, time_limit=3, est="~45 min",
                    inp="6\n1 2 1 3 2 1\n2\ncount 0 3\ncount 1 5", out="2\n3", expl="distinct counts in ranges (1-based)"),
    "CPP-130": dict(title="2-SAT Solver", cat="Graphs", diff="Hard", xp=230, coins=20, time_limit=3, est="~45 min",
                    inp="2\n1 -2\n-1 2", out="Satisfiable", expl="(x1 or !x2) and (!x1 or x2) is satisfiable"),
    "CPP-131": dict(title="Suffix Automaton", cat="Strings", diff="Hard", xp=231, coins=20, time_limit=3, est="~45 min",
                    inp="ababa", out="9", expl="number of distinct substrings"),
    "CPP-132": dict(title="Link-Cut Tree Basics", cat="Trees", diff="Hard", xp=232, coins=20, time_limit=3, est="~45 min",
                    inp="3\n0 1\n1 2\n2\nlink 0 2\nquery 0 2", out="Yes", expl="after link, 0 and 2 connected"),
    "CPP-133": dict(title="Treap Operations", cat="Balanced Trees", diff="Hard", xp=233, coins=20, time_limit=3, est="~45 min",
                    inp="5\ninsert 5\ninsert 2\ninsert 8\nsearch 8\nsearch 3", out="Yes\nNo", expl="search results"),
    "CPP-134": dict(title="AVL Tree Implementation", cat="Balanced Trees", diff="Hard", xp=234, coins=20, time_limit=3, est="~45 min",
                    inp="5\ninsert 5\ninsert 3\ninsert 7\ninsert 2\nheight", out="2", expl="AVL height after insertions"),
    "CPP-135": dict(title="Red-Black Tree Concepts", cat="Balanced Trees", diff="Hard", xp=235, coins=20, time_limit=3, est="~45 min",
                    inp="5\ninsert 7\ninsert 3\ninsert 18\ninsert 10\nblack_height 7", out="2", expl="black height of root"),
    "CPP-136": dict(title="Fast Matrix Exponentiation", cat="Math", diff="Hard", xp=236, coins=20, time_limit=3, est="~45 min",
                    inp="2\n1 1\n1 0", out="1 1\n1 0", expl="matrix to the power of 1"),
    "CPP-137": dict(title="Polynomial Rolling Hash", cat="Strings", diff="Hard", xp=237, coins=20, time_limit=3, est="~45 min",
                    inp="abcde abc", out="Yes", expl="abc is a substring of abcde"),
    "CPP-138": dict(title="FFT Polynomial Multiplication", cat="Math", diff="Hard", xp=238, coins=20, time_limit=3, est="~45 min",
                    inp="2 2\n1 2\n3 4", out="3 10 8", expl="(1+2x)(3+4x) = 3+10x+8x^2"),
    "CPP-139": dict(title="Chinese Remainder Theorem", cat="Number Theory", diff="Hard", xp=239, coins=20, time_limit=3, est="~45 min",
                    inp="3\n3 2\n5 3", out="8", expl="x=2 mod 3, x=3 mod 5 => x=8"),
    "CPP-140": dict(title="Miller-Rabin Primality Test", cat="Number Theory", diff="Hard", xp=240, coins=20, time_limit=3, est="~45 min",
                    inp="101", out="Prime", expl="101 is prime",
                    extra=[("91", "Composite", "91 = 7*13")]),
}


def build_description(title, inp, out, expl):
    return (
        f"**Task:** {title}.\n\n"
        f"**Input:**\n```\n{inp}\n```\n"
        f"**Expected output:**\n```\n{out}\n```\n"
        f"**Explanation:** {expl}\n\n"
        "Write a C++ program that reads the input from **stdin** and prints exactly the expected output to **stdout**."
    )


def main():
    sess = get_session()
    try:
        # idempotent: drop previous CPP-* rows and rebuild
        old = sess.query(Challenge).filter(Challenge.challenge_key.like("CPP-%")).all()
        for ch in old:
            for m in (ChallengeStarterCode, ChallengeExample, ChallengeTestCase):
                sess.query(m).filter(m.challenge_id == ch.id).delete()
            sess.delete(ch)
        sess.commit()
        print(f"Removed {len(old)} old CPP-* challenges")

        setting = sess.get(ChallengeSetting, GUILD_ID)
        if not setting:
            setting = ChallengeSetting(guild_id=GUILD_ID)
            sess.add(setting)
        setting.enabled = True
        setting.channel_id = setting.channel_id
        setting.embed_color = setting.embed_color or "#5865F2"
        setting.leaderboard_enabled = True
        setting.xp_enabled = True
        sess.flush()

        n = 0
        for key in sorted(SPECS.keys(), key=lambda k: int(k.split("-")[1])):
            s = SPECS[key]
            desc = build_description(s["title"], s["inp"], s["out"], s.get("expl", ""))
            ch = Challenge(
                challenge_key=key,
                title=s["title"],
                description=desc,
                language="C++",
                category=s["cat"],
                difficulty=s["diff"],
                enabled=True,
                time_limit=s["time_limit"],
                memory_limit=256,
                max_code_size=100000,
                ignore_trailing_spaces=True,
                ignore_empty_lines=True,
                case_sensitive=True,
                xp_reward=s["xp"],
                coins_reward=s["coins"],
                unlock_achievement=None,
                unlock_next_challenge=True,
                estimated_time=s.get("est", "~30 min"),
                total_attempts=0,
                successful_attempts=0,
                avg_solve_time=0.0,
            )
            sess.add(ch)
            sess.flush()

            sess.add(ChallengeStarterCode(challenge_id=ch.id, language="C++", code=CXX_STARTER))
            sess.add(ChallengeExample(challenge_id=ch.id, input=s["inp"], output=s["out"], explanation=s.get("expl", "")))
            # visible guessed test cases
            cases = [(s["inp"], s["out"], s.get("expl", ""))]
            for i, o, e in s.get("extra", []):
                cases.append((i, o, e))
            for i, o, e in cases:
                sess.add(ChallengeTestCase(challenge_id=ch.id, input=i, expected_output=o, hidden=False))
            n += 1

        sess.commit()
        print(f"Inserted {n} challenges into challenges DB (SQLite: data/dt_bot.db)" if not os.getenv("DATABASE_URL") else f"Inserted {n} challenges")
    finally:
        sess.close()


if __name__ == "__main__":
    main()
