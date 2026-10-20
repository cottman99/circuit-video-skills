#!/usr/bin/env python3
"""Balanced FFmpeg select expression for explicitly requested zero-based frames."""
import argparse


def balanced_select(indices):
    values = list(indices)
    if any(type(index) is not int or index < 0 for index in values):
        raise ValueError('Frame indices must be nonnegative integers')
    values = sorted(set(values))
    if not values:
        return '0'
    def tree(start, stop):
        if stop - start == 1:
            return f'eq(n\\,{values[start]})'
        middle = (start + stop) // 2
        return '(' + tree(start, middle) + '+' + tree(middle, stop) + ')'
    return tree(0, len(values))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('indices', type=int, nargs='*')
    args = parser.parse_args()
    try:
        print(balanced_select(args.indices))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
