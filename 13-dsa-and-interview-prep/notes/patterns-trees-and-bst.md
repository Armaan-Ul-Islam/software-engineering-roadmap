# Patterns: trees and binary search trees

> **In one sentence:** Tree problems are recursion problems: decide what one call returns about its subtree (a depth, a flag, a node), trust the recursive calls for the children and combine their answers; use a queue instead of recursion when the question is about levels; and for binary search trees carry the one invariant, "everything on the left is smaller, everything on the right is larger", down the tree as a pair of bounds.

**Why it matters:** Trees are where recursion that returns values is learned, and that is the skill behind dynamic programming, divide and conquer and graph DFS. Validate Binary Search Tree is the classic "looks trivial, most candidates get it wrong" question, because checking each node against its parent is not the same as checking it against every ancestor.

## The idea

The node used throughout (LeetCode's `TreeNode` calls the field `val`):

```java
public final class TreeNode {
    int value;
    TreeNode left;
    TreeNode right;

    TreeNode(int value) {
        this.value = value;
    }
}
```

**Recognising the shape.** "Depth", "height", "balanced", "diameter", "path sum", "same tree", "invert": recursive DFS that returns a value. "Level order", "zigzag", "right side view", "minimum depth", "connect nodes at the same level": BFS with a queue. "Validate", "kth smallest", "insert", "search", "lowest common ancestor in a BST": the BST invariant.

**Recursive DFS with return values.** Every solution has the same skeleton: a base case for `null`, recursive calls on the children, and a combination step. The combination decides the traversal order: combine after both calls (post-order, which most "compute something about the subtree" problems need), process the node first (pre-order, for copying or serialising), or in between (in-order, which visits a BST in sorted order).

```java
static int maxDepth(TreeNode root) {
    if (root == null) {
        return 0;
    }
    return 1 + Math.max(maxDepth(root.left), maxDepth(root.right));
}
```

That is Maximum Depth of Binary Tree (104). When one call must produce two facts (for Balanced Binary Tree, 110, both "is balanced" and "height"), return a record or encode the failure as a sentinel (-1 for "not balanced"), rather than running two separate recursions, which costs O(n^2) on a degenerate tree.

**BFS by level.** The one trick is to capture `queue.size()` before draining a level, because the queue grows while you process it. `ArrayDeque` rejects `null`, so children are checked before they are offered.

**BST invariants with bounds.** A node is valid when `low < value < high`, where the bounds come from the ancestors: going left tightens `high` to the parent's value, going right tightens `low`. Alternatively, an in-order traversal of a valid BST produces a strictly increasing sequence. Searching a BST discards one subtree per step, so operations cost O(h), where `h` is the height: O(log n) for a balanced tree and O(n) for a degenerate one.

**Complexity.** DFS and BFS both visit every node once: O(n) time. DFS uses O(h) stack; BFS uses O(w) for the queue, where `w` is the widest level, up to n/2 in a complete tree.

## Example: Validate Binary Search Tree (98)

The tree that breaks parent-only checking:

```text
      5
     / \
    1   7
       / \
      4   8
```

Node 4 is smaller than its parent 7, so a local check passes, but 4 sits in the right subtree of 5 and is therefore invalid. The bounds version catches it because the right subtree of 5 inherits `low = 5`.

```java
public final class ValidateBinarySearchTree {

    public boolean isValidBST(TreeNode root) {
        return isWithin(root, Long.MIN_VALUE, Long.MAX_VALUE);
    }

    private boolean isWithin(TreeNode node, long exclusiveLow, long exclusiveHigh) {
        if (node == null) {
            return true;
        }
        if (node.value <= exclusiveLow || node.value >= exclusiveHigh) {
            return false;
        }
        return isWithin(node.left, exclusiveLow, node.value)
                && isWithin(node.right, node.value, exclusiveHigh);
    }
}
```

The bounds are `long` because node values may be any `int`, including `Integer.MIN_VALUE` and `Integer.MAX_VALUE`; with `int` bounds a single-node tree holding `Integer.MAX_VALUE` would wrongly fail. The `<=` and `>=` make duplicates invalid, which is what the problem requires.

## Example: Binary Tree Level Order Traversal (102)

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public final class LevelOrderTraversal {

    public List<List<Integer>> levelOrder(TreeNode root) {
        List<List<Integer>> levels = new ArrayList<>();
        if (root == null) {
            return levels;
        }
        Deque<TreeNode> queue = new ArrayDeque<>();
        queue.offer(root);
        while (!queue.isEmpty()) {
            int levelSize = queue.size();
            List<Integer> level = new ArrayList<>(levelSize);
            for (int indexInLevel = 0; indexInLevel < levelSize; indexInLevel++) {
                TreeNode node = queue.poll();
                level.add(node.value);
                if (node.left != null) {
                    queue.offer(node.left);
                }
                if (node.right != null) {
                    queue.offer(node.right);
                }
            }
            levels.add(level);
        }
        return levels;
    }
}
```

For the tree `3 (9, 20 (15, 7))` the result is `[[3], [9, 20], [15, 7]]`. The same loop with `levels.add(level.get(level.size() - 1))` gives Binary Tree Right Side View (199), and reversing every other level gives Zigzag Level Order Traversal (103).

## Example: Lowest Common Ancestor of a Binary Search Tree (235)

In a BST the LCA of two nodes is the first node on the path from the root whose value lies between them (inclusive). No recursion needed, and the loop is O(h).

```java
public final class LowestCommonAncestorOfBst {

    public TreeNode lowestCommonAncestor(TreeNode root, TreeNode first, TreeNode second) {
        TreeNode current = root;
        while (current != null) {
            if (first.value < current.value && second.value < current.value) {
                current = current.left;
            } else if (first.value > current.value && second.value > current.value) {
                current = current.right;
            } else {
                return current;
            }
        }
        return null;
    }
}
```

In the BST `6 (2 (0, 4 (3, 5)), 8 (7, 9))`, the LCA of 2 and 8 is 6 (the values split at the root) and the LCA of 2 and 4 is 2 (a node is its own ancestor). The general binary tree version (236) has no ordering to exploit: it is a post-order recursion that returns the node if the current node is one of the targets, otherwise the non-null child result, or the current node itself when both children return something.

## Pitfalls

- Validating a BST against the parent only. The counterexample above is the one interviewers draw when you do; carry bounds or use in-order.
- `int` bounds initialised to `Integer.MIN_VALUE` and `Integer.MAX_VALUE`. A node holding one of those values fails the `<=` test. Use `long`, or `Integer` bounds with `null` meaning "unbounded".
- Reading `queue.size()` inside the loop condition. The size changes as children are added; capture it in `levelSize` first.
- Offering `null` children to an `ArrayDeque`. It throws `NullPointerException` immediately; `LinkedList` would accept the `null` and fail later on `node.value`.
- Confusing depth in nodes with depth in edges. LeetCode counts nodes (a single node has depth 1); some textbooks count edges. Say which you are using.
- Mixing a return value with a mutated field (a `maxDiameter` field updated inside the recursion) and forgetting to reset the field between test cases, or making the method non-reentrant. It is a legitimate technique; just be deliberate about it.
- Recursion on a degenerate tree. A path of 10^5 nodes is 10^5 frames; LeetCode's tree problems stay at 10^4 nodes, but a real system should use an explicit stack.
- Using the BST version of LCA on a plain binary tree. It walks the wrong way as soon as the ordering assumption fails, and returns a wrong node rather than an error.

## Check yourself

1. What does `isWithin` pass as the bounds for the left child of a node with value 7 whose own bounds are (5, 10), and why does that catch the counterexample tree?
2. Balanced Binary Tree (110) needs both the height and whether a subtree is balanced. Write the return type you would use, or the sentinel, and explain why a separate height recursion per node is O(n^2).
3. In the level-order code, what output would you get if `levelSize` were replaced by `queue.size()` in the `for` condition? Trace it on a tree with three levels.
4. The in-order traversal of a tree is `1, 3, 3, 4`. Is it a valid BST under LeetCode's definition? Which comparison in an in-order validator decides that?

## Go deeper

- [Tech Interview Handbook: Tree cheatsheet](https://www.techinterviewhandbook.org/algorithms/tree/) · the traversal orders, the common techniques and the corner cases to mention.
- [VisuAlgo: Binary Search Tree](https://visualgo.net/en/bst) · animate insertion, deletion and search; watch what a degenerate tree looks like.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Trees node has the four problems in this note and the serialisation and diameter follow-ups.

---

Part of [DSA & Interviews](../README.md) · item 3.2
