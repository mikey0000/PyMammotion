# Technical Documentation: Advanced Techniques & Workarounds

This document covers advanced techniques that a developer can use to achieve complex behaviors by combining the robot's standard capabilities in novel ways. These methods require more complex application-side logic but can unlock functionality not directly exposed in the API.

---

## The "Path-as-a-Map" Technique for Custom Patterns

In the `developer_guide.md`, we discussed using an external path-following controller to execute custom mowing patterns. That method offers the highest degree of real-time control. However, there is another, cleverer workaround that may be simpler for certain use cases: **tricking the robot's internal planner into following your custom path by creating a map that looks like a long, thin corridor.**

The core idea is to programmatically generate and upload a map that defines a very narrow area to be mowed, where the shape of that area *is* the custom path you want to execute.

### The Concept

Imagine you want the robot to mow a perfect spiral. Instead of remote-controlling it, you would create a map with two boundaries: an "outer spiral" and an "inner spiral". The space between these two boundaries is a single, continuous, narrow channel.

When you command the robot to "mow" this area, its internal planner has no choice but to follow the channel from one end to the other, effectively executing your spiral pattern.

#### Visual Example (Spiral Pattern)

```
      #####################
      #                   #
      #   ###############   #
      #   #             #   #
      #   #   #######   #   #
      #   #   #     #   #   #
      #   #   #     #####   #
      #   #   #             #
      #   #   ###############
      #   #
      #####

Legend:
# = Map Boundary (No-Go Zone)
  = The "Channel" (The only area the robot is allowed to mow)
```

### Step-by-Step Implementation Guide

1.  **Generate the Path Locally:** Your application first generates the desired custom path as a series of `(x, y)` waypoints. Let's call this the `centerline_path`.

2.  **Generate the Corridor Boundaries:** From the `centerline_path`, your application generates two new sets of points:
    *   An `outer_boundary` by offsetting each point in the `centerline_path` outwards (e.g., perpendicular to the path direction by `+mower_width / 2`).
    *   An `inner_boundary` by offsetting each point inwards (e.g., perpendicular to the path direction by `-mower_width / 2`).
    *   These two lists of points now define your "corridor".

3.  **Upload the Corridor as a Map:** Your application must use the map editing protocol to create a new task area defined by these boundaries. This is a multi-step process:
    a. Send `NavGetCommData` (`action=0, type=0`) to start drawing a new boundary.
    b. Send the points for the `outer_boundary` to the robot. (The exact message for sending point data during a draw is not explicitly defined in the protos I've seen, this would require experimentation. It's likely a `NavEdgePoints` or similar message).
    c. Send `NavGetCommData` (`action=1, type=0`) to finish the first boundary.
    d. Repeat steps a-c for the `inner_boundary`, creating it as a no-go zone (obstacle) inside the first boundary.
    e. Send a command to save the new map.

4.  **Execute the Mow:** Once the special "corridor map" is saved on the robot, send a standard `NavStartJob` command, targeting the `jobId` of the new map.

5.  **Clean Up:** After the job is complete, your application should probably delete the special-purpose map to avoid cluttering the user's map list.

### Required Protocol Messages:

-   **Map Creation:** `NavGetCommData` (to start/stop drawing boundaries and obstacles). The exact message for sending the stream of points during a drawing operation needs to be determined experimentally but is a key part of the existing map creation flow.
-   **Task Execution:** `NavStartJob` (to command the robot to mow the newly created map area).

### Limitations and Considerations:

-   **Complexity:** The logic for generating the boundary points and programmatically uploading a map is non-trivial.
-   **Upload Time:** Creating a new, complex map on the robot might be a slow process. This technique is better suited for pre-planned, complex jobs rather than dynamic, real-time paths.
-   **Planner Limitations:** The robot's internal planner might have issues with extremely narrow or complex corridors with very sharp turns. This would require testing to find the limits.
-   **Advantage:** The main advantage of this technique over the "remote control" method is that once the job is started, the robot is autonomous. The application does not need to maintain a constant, high-frequency connection to guide it, which can be more reliable.
