# Patterns: linked lists

> **In one sentence:** Nearly every linked-list problem is a combination of four moves (a dummy head so the first node is not a special case, a fast and a slow pointer to find the middle or a cycle, in-place reversal with three references, and merging by splicing nodes onto a tail), and every bug is in the order you update the references.

**Why it matters:** Linked lists are rare in production Java (`ArrayList` almost always wins, and `LinkedList` is usually a mistake), but they remain a favourite interview filter because they test whether you can manipulate references carefully, draw what you are doing, and handle `null`. Reorder List combines three of the four moves and is the classic "medium that feels hard" until you see it as composition.

## The idea

The problems use a minimal node. LeetCode calls the value field `val`; here it is spelled out.

```java
public final class ListNode {
    int value;
    ListNode next;

    ListNode(int value) {
        this.value = value;
    }
}
```

**Move 1: the dummy head.** Any time you build a list or may delete the first node, start from `ListNode dummyHead = new ListNode(0)`, work with `tail` or `previous` references, and return `dummyHead.next`. The head stops being a special case.

**Move 2: fast and slow pointers.** `slow` advances one node per step, `fast` two. When `fast` reaches the end, `slow` is at the middle. If `fast` ever meets `slow`, the list has a cycle (Floyd's algorithm): once both are inside the cycle, the gap shrinks by one each step, so they meet within one lap. There are two loop conditions and they land on different middles for even lengths:

```java
while (fast != null && fast.next != null) {        // slow ends on the second middle: 1 2 [3] 4
    slow = slow.next;
    fast = fast.next.next;
}
```

```java
while (fast.next != null && fast.next.next != null) {   // slow ends on the first middle: 1 [2] 3 4
    slow = slow.next;
    fast = fast.next.next;
}
```

Advancing `fast` by `k` nodes first makes `slow` stop `k` nodes from the end (Remove Nth Node From End of List, 19).

**Move 3: in-place reversal.** Three references: `previous`, `current`, and the saved `next`. Save `next` before you overwrite `current.next`.

**Move 4: merging.** A dummy head plus a `tail`; at each step, attach the smaller head to `tail`, advance that list, advance `tail`. When one list is exhausted, attach the rest of the other.

**Complexity.** All four moves are O(n) time and O(1) extra space. Recursive reversal is also O(n) time but uses O(n) stack, which is a `StackOverflowError` on a 10^5-node list.

## Example: Reverse Linked List (206) and Merge Two Sorted Lists (21)

```java
public final class ListOperations {

    static ListNode reverse(ListNode head) {
        ListNode previous = null;
        ListNode current = head;
        while (current != null) {
            ListNode next = current.next;
            current.next = previous;
            previous = current;
            current = next;
        }
        return previous;
    }

    static ListNode mergeTwoLists(ListNode first, ListNode second) {
        ListNode dummyHead = new ListNode(0);
        ListNode tail = dummyHead;
        while (first != null && second != null) {
            if (first.value <= second.value) {
                tail.next = first;
                first = first.next;
            } else {
                tail.next = second;
                second = second.next;
            }
            tail = tail.next;
        }
        tail.next = first != null ? first : second;
        return dummyHead.next;
    }
}
```

Reversing `1 -> 2 -> 3`: after the first iteration `1 -> null` and `current` is 2; after the second `2 -> 1 -> null`; after the third `3 -> 2 -> 1 -> null`, `current` is `null`, and `previous` (3) is the new head. Merging `1 -> 2 -> 4` with `1 -> 3 -> 4` gives `1 -> 1 -> 2 -> 3 -> 4 -> 4`; the `<=` keeps the merge stable, taking from `first` on ties.

## Example: Linked List Cycle (141)

```java
public final class LinkedListCycle {

    public boolean hasCycle(ListNode head) {
        ListNode slow = head;
        ListNode fast = head;
        while (fast != null && fast.next != null) {
            slow = slow.next;
            fast = fast.next.next;
            if (slow == fast) {
                return true;
            }
        }
        return false;
    }
}
```

`slow == fast` compares references, which is exactly right here: two different nodes with the same value are not a cycle. The alternative, a `HashSet<ListNode>` of visited nodes, is O(n) space and also correct because `ListNode` does not override `equals`, so the set compares identities. To find where the cycle starts (Linked List Cycle II, 142), reset one pointer to `head` after they meet and advance both one step at a time; they meet at the entry node.

## Example: Reorder List (143)

Turn `L0 -> L1 -> ... -> Ln` into `L0 -> Ln -> L1 -> Ln-1 -> ...` in place. Three moves in sequence: find the middle, reverse the second half, interleave.

```java
public final class ReorderList {

    public void reorderList(ListNode head) {
        if (head == null || head.next == null) {
            return;
        }
        ListNode slow = head;
        ListNode fast = head;
        while (fast.next != null && fast.next.next != null) {
            slow = slow.next;
            fast = fast.next.next;
        }
        ListNode secondHalf = ListOperations.reverse(slow.next);
        slow.next = null;

        ListNode first = head;
        ListNode second = secondHalf;
        while (second != null) {
            ListNode firstNext = first.next;
            ListNode secondNext = second.next;
            first.next = second;
            second.next = firstNext;
            first = firstNext;
            second = secondNext;
        }
    }
}
```

For `1 -> 2 -> 3 -> 4`: `slow` stops at 2 (the first-middle variant), the second half `3 -> 4` becomes `4 -> 3`, cutting `slow.next` leaves `1 -> 2`, and interleaving gives `1 -> 4 -> 2 -> 3`. For `1 -> 2 -> 3 -> 4 -> 5`: `slow` stops at 3, the second half `4 -> 5` becomes `5 -> 4`, and the result is `1 -> 5 -> 2 -> 4 -> 3`. Using the first middle guarantees the first half is never shorter than the second, so the interleaving loop can stop when `second` runs out.

## Pitfalls

- Overwriting `next` before saving it. The rest of the list is unreachable and garbage collected; the symptom is a list that ends early. Write the save line first, always.
- Forgetting to cut the first half (`slow.next = null`) in Reorder List. The result contains a cycle and printing it never ends.
- Mixing up the two middle variants. The second-middle loop in Reorder List makes the second half longer than the first for even lengths, and the interleaving loop then drops a node or dereferences `null`.
- Special-casing the head instead of using a dummy. Deletion and insertion code without a dummy head has an `if (head.value == target)` branch that is a second copy of the main logic, and the two copies drift apart.
- Recursive reversal or recursive merge on long lists. Correct, elegant, and a `StackOverflowError` on LeetCode's larger inputs.
- Comparing values when you mean nodes, or nodes when you mean values. `slow == fast` is a reference comparison and is correct for cycle detection; `first.value <= second.value` is a value comparison and is correct for merging.
- Losing track of where `tail` is. After `tail.next = first`, `tail` must move (`tail = tail.next`), otherwise every iteration overwrites the same link.
- Confusing this structure with `java.util.LinkedList`. That class is a doubly linked list with O(n) `get(index)`, and nothing in this note applies to it; when you need a queue or deque in Java, use `ArrayDeque`.

## Check yourself

1. In `reverse`, what is the state of `previous`, `current` and `next` after two iterations on `1 -> 2 -> 3 -> 4`? Draw it.
2. Why does Floyd's algorithm terminate? Give the one-sentence argument about the gap between the two pointers.
3. Reorder List with the second-middle loop variant: what goes wrong on `1 -> 2 -> 3 -> 4`, step by step?
4. Remove Nth Node From End of List (19) in one pass: where do you start `fast`, how far ahead, and why does the dummy head matter when `n` equals the length of the list?

## Go deeper

- [Tech Interview Handbook: Linked list cheatsheet](https://www.techinterviewhandbook.org/algorithms/linked-list/) · the techniques above in summary form, plus the corner cases interviewers probe.
- [VisuAlgo: Linked List](https://visualgo.net/en/list) · animate insertions, deletions and reversal until the pointer updates are automatic.
- [Python Tutor](https://pythontutor.com/) · supports Java; step through `reverse` and watch the three references move.

---

Part of [DSA & Interviews](../README.md) · item 3.1
