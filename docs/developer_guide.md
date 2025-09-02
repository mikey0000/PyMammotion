# Developer Guide: Implementing Advanced Capabilities

## Introduction

The `pymammotion` protocol is remarkably rich and provides a vast amount of real-time data and low-level control commands. While the core library provides high-level functions for common tasks like mowing a pre-defined area, the true power of the robot can be unlocked by combining the raw protocol capabilities to create novel and intelligent behaviors.

This guide is intended for developers who want to go beyond the standard API and implement their own advanced features. It provides conceptual guides and pseudo-code for several powerful scenarios.

**A Note on Possibility:** Everything described in this guide is based strictly on the data and commands confirmed to be available in the protobuf definitions. No capabilities have been invented or assumed. These scenarios represent what is **possible** by building custom application logic on top of the raw protocol building blocks.

---

## Scenario 1: Dynamic Obstacle Avoidance

The robot's built-in navigation can avoid obstacles on the pre-defined map. However, by using the real-time perception data, a developer can create a system that reacts to new, unexpected obstacles (e.g., a toy left on the lawn, a temporary garden hose).

The core logic is to monitor for new obstacles in the robot's path, pause the job, manually navigate around the obstacle, and then resume the job from the new position.

### Required Protocol Messages:

1.  **To Receive Obstacle Data:** `perception_obstacles_visualization_t`
    -   This message, documented in `perception.md`, provides a list of labeled obstacles and their boundaries in real-time.
2.  **To Receive Robot Position:** `NavPosUp`
    -   This message, documented in `state_and_status.md`, provides the robot's current `(x, y)` position and `heading`.
3.  **To Control the Job:** `NavTaskCtrl`
    -   This message, documented in `task_control.md`, is used to pause (`action=2`) and resume (`action=9`, "Continue from Anywhere") the job.
4.  **To Manually Move the Robot:** `DrvMotionCtrl`
    -   This message, documented in `task_control.md`, allows you to set the robot's linear and angular speed for manual navigation.

### Conceptual Implementation (Pseudo-code)

This pseudo-code illustrates how an application could manage this logic.

```python
# Main application loop
def dynamic_avoidance_loop():
    while robot.is_mowing():
        # 1. Get real-time data
        live_obstacles = robot.get_live_obstacles() # From perception_obstacles_visualization_t
        robot_position = robot.get_position()       # From NavPosUp
        predicted_path = robot.get_predicted_path() # Application-level logic to predict path

        # 2. Check for imminent collision
        imminent_collision = False
        for obstacle in live_obstacles:
            if path_intersects_obstacle(predicted_path, obstacle):
                imminent_collision = True
                colliding_obstacle = obstacle
                break

        if imminent_collision:
            # 3. Collision detected, take action
            print(f"Collision predicted with obstacle: {colliding_obstacle.label}")

            # Pause the current mowing job
            robot.send_command(NavTaskCtrl(type=1, action=2)) # Pause

            # Calculate a path around the obstacle (this is complex application logic)
            avoidance_path = calculate_avoidance_path(robot_position, colliding_obstacle)

            # Manually drive the robot along the avoidance path
            for waypoint in avoidance_path:
                go_to_waypoint(waypoint, robot) # Uses DrvMotionCtrl in a feedback loop

            # Resume the job from the new position
            robot.send_command(NavTaskCtrl(type=1, action=9)) # Continue from Anywhere

            print("Avoidance maneuver complete, job resumed.")

        # Sleep for a short duration to avoid spamming commands
        time.sleep(0.2)

def go_to_waypoint(target_waypoint, robot):
    # This is a simplified path-following controller loop
    while distance(robot.get_position(), target_waypoint) > 0.1: # 10cm tolerance
        # Calculate angle to target and distance
        angle_to_target = calculate_angle(robot.get_position(), target_waypoint)
        current_heading = robot.get_position().heading

        # Calculate required turn and speed
        turn_speed = (angle_to_target - current_heading) * GAIN_P # Proportional controller
        forward_speed = 0.2 # Constant forward speed for simplicity

        # Send manual movement command
        robot.send_command(DrvMotionCtrl(setLinearSpeed=forward_speed, setAngularSpeed=turn_speed))
        time.sleep(0.1)

    # Stop the robot at the waypoint
    robot.send_command(DrvMotionCtrl(setLinearSpeed=0, setAngularSpeed=0))

```

This example demonstrates how combining perception data with job and motor control commands can create a sophisticated behavior that is far more advanced than the robot's default capabilities.

---

## Scenario 2: Custom Mowing Pattern

The robot's internal path planner is sophisticated, but a developer might want to implement a custom mowing pattern (e.g., a spiral, a single pass around the perimeter, or a pattern optimized for a specific application). The protocol makes this possible by providing the necessary building blocks for an external path-following controller.

The core concept is to treat the robot as a remote-controlled object. The developer's application will be responsible for the "brain," continuously telling the robot how to move to stay on the custom path.

### Required Protocol Messages:

1.  **To Receive Robot Position:** `NavPosUp`
    -   This is the most critical message, providing the real-time `(x, y)` position and `heading` needed for the feedback loop.
2.  **To Manually Move the Robot:** `DrvMotionCtrl`
    -   This message allows the application to continuously adjust the robot's linear (forward/backward) and angular (turning) speed.
3.  **To Control the Cutter:** `DrvMowCtrlByHand` (from `mctrl_driver.proto`)
    -   This message is used to turn the cutting blades on (`main_ctrl=1`) and off (`main_ctrl=0`) independently of the robot's movement.

### Conceptual Implementation (Pseudo-code)

This pseudo-code illustrates a simple waypoint-following controller.

```python
# Define a custom path as a list of waypoints
custom_path = [(10, 20), (10, 30), (12, 30), (12, 20)]

def execute_custom_mowing_pattern(path):
    # Ensure the cutter is on before starting
    robot.send_command(DrvMowCtrlByHand(main_ctrl=1))

    # Loop through each waypoint in the path
    for waypoint in path:
        print(f"Moving to waypoint: {waypoint}")
        go_to_waypoint(waypoint, robot) # Use the same feedback controller as before

    print("Custom mowing pattern complete.")

    # Turn off the cutter
    robot.send_command(DrvMowCtrlByHand(main_ctrl=0))

    # Command the robot to return to the dock
    robot.send_command(NavTaskCtrl(type=1, action=5)) # Return to Dock

def go_to_waypoint(target_waypoint, robot):
    # This is a simplified path-following controller loop.
    # A real implementation would use a more advanced controller (e.g., PID).
    while distance(robot.get_position(), target_waypoint) > 0.1: # 10cm tolerance
        # Get current state
        current_pos = robot.get_position() # From NavPosUp
        current_heading = current_pos.heading

        # Calculate angle and distance to target
        angle_to_target = calculate_angle(current_pos, target_waypoint)
        distance_to_target = distance(current_pos, target_waypoint)

        # --- Proportional Control Logic ---
        # Turn faster if the angle error is large
        angle_error = angle_to_target - current_heading
        turn_speed = angle_error * P_GAIN_TURN

        # Move faster if far away, but slow down when close
        forward_speed = distance_to_target * P_GAIN_SPEED
        # Clamp speed to a maximum value
        forward_speed = min(forward_speed, MAX_SPEED)

        # Send the command
        robot.send_command(DrvMotionCtrl(setLinearSpeed=forward_speed, setAngularSpeed=turn_speed))

        time.sleep(0.1) # Loop at 10Hz

    # Stop the robot when the waypoint is reached
    robot.send_command(DrvMotionCtrl(setLinearSpeed=0, setAngularSpeed=0))

```

This scenario demonstrates that a developer is not limited to the robot's built-in mowing patterns. By implementing a standard robotics feedback controller, any custom path or behavior can be achieved.

---

## Scenario 3: "Follow Me" Mode

A "follow me" mode is a classic robotics feature that can be implemented using the same building blocks as the custom mowing pattern. In this scenario, the "custom path" is simply the real-time location of a target, such as the user's mobile phone.

The core logic is to continuously compare the robot's position with the target's position and send movement commands to close the distance and match the heading.

### Required Protocol Messages:

1.  **To Receive Robot Position:** `NavPosUp`
    -   Provides the robot's real-time `(x, y)` position and `heading`.
2.  **To Manually Move the Robot:** `DrvMotionCtrl`
    -   Allows the application to send continuous adjustments to the robot's speed and turning rate.

### Required External Data:

-   **Target's Position:** The application needs a source for the target's real-time location (e.g., the GPS from the phone running the application).

### Conceptual Implementation (Pseudo-code)

This pseudo-code illustrates the main control loop for a "follow me" mode.

```python
# Constants
FOLLOW_DISTANCE = 2.0  # The robot will try to stay 2 meters away from the target
MAX_SPEED = 0.5        # Maximum speed in meters/sec
P_GAIN_TURN = 0.8      # Proportional gain for turning
P_GAIN_SPEED = 0.4     # Proportional gain for forward speed

def follow_me_loop():
    print("Starting 'Follow Me' mode. Press Ctrl+C to stop.")
    try:
        while True:
            # 1. Get real-time data
            robot_pos = robot.get_position()       # From NavPosUp
            target_pos = phone.get_gps_position()  # From the application's device

            # 2. Calculate error between robot and target
            distance_to_target = distance(robot_pos, target_pos)
            angle_to_target = calculate_angle(robot_pos, target_pos)

            # --- Proportional Control Logic ---

            # Calculate heading error
            heading_error = angle_to_target - robot_pos.heading
            turn_speed = heading_error * P_GAIN_TURN

            # Calculate distance error
            distance_error = distance_to_target - FOLLOW_DISTANCE
            forward_speed = distance_error * P_GAIN_SPEED

            # 3. Apply constraints
            # Don't move if the target is very close
            if distance_to_target < FOLLOW_DISTANCE:
                forward_speed = 0

            # Clamp speed to a maximum value
            forward_speed = min(forward_speed, MAX_SPEED)

            # 4. Send command to robot
            robot.send_command(DrvMotionCtrl(setLinearSpeed=forward_speed, setAngularSpeed=turn_speed))

            time.sleep(0.1) # Loop at 10Hz

    except KeyboardInterrupt:
        print("Stopping 'Follow Me' mode.")
        # Stop the robot when the loop is exited
        robot.send_command(DrvMotionCtrl(setLinearSpeed=0, setAngularSpeed=0))

```

This example shows how a sophisticated, interactive behavior can be built entirely on the client side by combining the robot's positioning data with an external data source and the low-level motion control commands.
