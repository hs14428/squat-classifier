import cv2
import mediapipe as mp
import time
import numpy as np
import PoseLandmark as pl
import math
from collections import deque


# Mediapipe recommends at least 480h x 360w resolution. Lower res == improved latency
def resize_frame(frame):
    h, w, c = frame.shape
    # print("start: ",frame.shape)
    if h < 480 and w < 360:
        dimensions = (360, 480)
        frame = cv2.resize(frame, dimensions)
    elif w < 360:
        dimensions = (360, h)
        frame = cv2.resize(frame, dimensions)
    elif h < 480:
        dimensions = (w, 480)
        frame = cv2.resize(frame, dimensions)
    elif h > 1280 and w > 720:
        dimensions = (720, 1280)
        frame = cv2.resize(frame, dimensions)
    elif w > 720:
        dimensions = (720, h)
        frame = cv2.resize(frame, dimensions)
    elif h > 1280:
        dimensions = (w, 1280)
        frame = cv2.resize(frame, dimensions)
    # Manual resize for testing
    if h == 1280:
        frame = cv2.resize(frame, (480, 848))
    # print("end: ", frame.shape)
    return frame


def add_fps(frame, prev_time, frame_num):
    # Pin fps to frame
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time
    cv2.putText(frame, "Num: " + str(int(frame_num)), (5, 75),
                cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 2)
    cv2.putText(frame, "fps: " + str(int(fps)), (5, 110),
                cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 2)
    return prev_time


class PoseDetector():

    def __init__(self, static_image_mode=False, model_complexity=1, smooth=True,
                 detection_conf=0.5, tracking_conf=0.5):

        # Mediapipe pose parameters set up
        self.static_image_mode = static_image_mode
        self.model_complexity = model_complexity
        self.smooth = smooth
        self.detectionConf = detection_conf
        self.trackingConf = tracking_conf

        # Mediapipe drawing pose connection initialisation
        self.mpDraw = mp.solutions.drawing_utils
        self.mpPose = mp.solutions.pose
        self.pose = self.mpPose.Pose(self.static_image_mode, self.model_complexity, self.smooth,
                                     self.detectionConf, self.trackingConf)

        # Stores either all or specific pose landmark position enumerations
        self.landmark_connections = pl.PoseLandmark()
        # Stores the output of pose processing from mediapipe
        self.results = None
        # Stores the actual individual landmark x, y, z output
        self.landmarks = None
        # Store the min and max x, y values for the bounding box from pose landmark
        self.min_box_values, self.max_box_values = (0, 0), (0, 0)
        # Custom list for storing all converted landmark data
        self.landmark_list = []
        # Custom dict for storing orientation specific converted landmark data
        self.frame_landmarks = {}
        # Pose dictionary containing relevant frame pose details for analysis
        self.pose_data = {}
        # Sets the orientation of the video
        self.face_right = True

        # Rep count variable
        self.count = 0
        # Variable to set the direction of movement of squatter
        self.squat_direction = "Down"
        # Max length of barbell tracking points collection
        self.barbell_pts_len = 100
        # Set up the barbell tracking points collection with maxLen. > maxLen points == remove from tail end of points
        self.barbell_pts = deque(maxlen=self.barbell_pts_len)
        # Count for frames without circle/plate detected used to clear tracking queue
        self.no_circle = 0

    def find_box_coordinates(self, frame):
        h, w, c = frame.shape
        x_max, y_max = 0, 0
        x_min, y_min = w, h
        for landmark in self.landmarks.landmark:
            x, y = int(landmark.x * w), int(landmark.y * h)
            if x > x_max:
                x_max = x
            if x < x_min:
                x_min = x
            if y > y_max:
                y_max = y
            if y < y_min:
                y_min = y
        # Perhaps not needed?
        box_length = y_max - y_min
        # An average person is generally 7-and-a-half heads tall (including the head) - wikipedia. Thus head length:
        head_length = box_length / 7.5
        # Add half a head to have box capture top of head
        y_min = int(y_min - head_length / 2)
        return (x_min, y_min), (x_max, y_max)

    def find_pose(self, frame, draw=True, box=False):
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.pose.process(frame_rgb)
        self.landmarks = self.results.pose_landmarks
        pose_connections = self.landmark_connections.POSE_CONNECTIONS
        if self.landmarks:
            if draw:
                self.mpDraw.draw_landmarks(frame, self.landmarks, pose_connections)
            if box:
                self.min_box_values, self.max_box_values = self.find_box_coordinates(frame)
                cv2.rectangle(frame, self.min_box_values, self.max_box_values, (0, 255, 0), 2)
        return frame

    def find_positions(self, frame, specific=False, draw=False):
        if self.landmarks:
            for i, landmark in enumerate(self.landmarks.landmark):
                h, w, c = frame.shape
                cx, cy = int(landmark.x * w), int(landmark.y * h)
                if not specific:
                    # Store all landmark points
                    self.landmark_list.append([i, cx, cy])
                else:
                    # Store orientation specific landmark points
                    if i in self.landmark_connections.LANDMARKS:
                        self.frame_landmarks[i] = (i, cx, cy)
                if draw:
                    cv2.circle(frame, (cx, cy), 5, (255, 0, 0), cv2.FILLED)

    def find_angles(self, frame_num, p1, p2, p3, knee=True, draw=True):
        # Get the landmarks for each frame
        if p1 in self.pose_data[frame_num][1] and p2 in self.pose_data[frame_num][1] \
                and p3 in self.pose_data[frame_num][1]:
            frame = self.pose_data[frame_num][0]
            x1, y1 = self.pose_data[frame_num][1][p1][1:]
            x2, y2 = self.pose_data[frame_num][1][p2][1:]
            x3, y3 = self.pose_data[frame_num][1][p3][1:]

            # Get the angle between the points in question
            angle = math.degrees(math.atan2(y3 - y2, x3 - x2) -
                                 math.atan2(y1 - y2, x1 - x2))
            # Make appropriate adjustments based on squatter orientation
            if self.face_right:
                if knee:
                    angle = angle - 180
            else:
                if knee:
                    angle = 180 - angle
                else:
                    angle = 360 - angle

            if draw:
                cv2.line(frame, (x1, y1), (x2, y2), (255, 255, 255), 3)
                cv2.line(frame, (x3, y3), (x2, y2), (255, 255, 255), 3)
                cv2.circle(frame, (x1, y1), 10, (0, 0, 255), cv2.FILLED)
                cv2.circle(frame, (x1, y1), 15, (0, 0, 255), 2)
                cv2.circle(frame, (x2, y2), 10, (0, 0, 255), cv2.FILLED)
                cv2.circle(frame, (x2, y2), 15, (0, 0, 255), 2)
                cv2.circle(frame, (x3, y3), 10, (0, 0, 255), cv2.FILLED)
                cv2.circle(frame, (x3, y3), 15, (0, 0, 255), 2)
                cv2.putText(frame, str(int(angle)), (x2 - 80, y2 + 10),
                            cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
            return angle

    def draw_angles(self, frame_num, reps=False):
        p1, p2, p3 = self.landmark_connections.HIP_ANGLE_CONNECTIONS
        self.find_angles(frame_num, p1, p2, p3, knee=False, draw=True)
        p1, p2, p3 = self.landmark_connections.KNEE_ANGLE_CONNECTIONS
        angle = self.find_angles(frame_num, p1, p2, p3, knee=True, draw=True)

        if reps:
            self.rep_counter(angle)

    # Issues if the camera angle is slight off angle, and knee doesnt get to > 90 degrees
    # Maybe can return bottom of squat based of bound box and max knee angle
    # Maybe check if e.g. left foot index x is further ahead of right foot index (for face right)
    # If it is, indicates the the angle of camera is slightly off side
    def rep_counter(self, angle):
        # Calc percentage of way through rep, based off knee angle; 110 knee angle min for good squat
        rep_percentage = np.interp(angle, (15, 110), (0, 100))
        # print(angle, rep_percentage)

        # Check how far through rep squatter is
        if rep_percentage == 100:
            if self.squat_direction == "Down":
                self.count += 0.5
                self.squat_direction = "Up"
        if rep_percentage == 0:
            if self.squat_direction == "Up":
                self.count += 0.5
                self.squat_direction = "Down"

    # Determine whether squatter is facing left or right. Default is right
    # Needs work to improve for e.g. AC_FSL.mp4
    def get_orientation(self, frame):
        self.find_pose(frame, draw=False)
        self.find_positions(frame)
        # Extract x values for the shoulders and nose to compare
        if len(self.landmark_list) != 0:
            # right_shoulder_x = self.landmark_list[self.landmark_connections.RIGHT_SHOULDER][1]
            # left_shoulder_x = self.landmark_list[self.landmark_connections.LEFT_SHOULDER][1]
            # nose_x = self.landmark_list[self.landmark_connections.NOSE][1]
            right_heel_x = self.landmark_list[self.landmark_connections.RIGHT_HEEL][1]
            left_heel_x = self.landmark_list[self.landmark_connections.LEFT_HEEL][1]
            right_foot_index_x = self.landmark_list[self.landmark_connections.RIGHT_FOOT_INDEX][1]
            left_foot_index_x = self.landmark_list[self.landmark_connections.LEFT_FOOT_INDEX][1]
            # If the nose is further along the x axis than either shoulders, facing right
            if (right_foot_index_x > right_heel_x) or (left_foot_index_x > left_heel_x):
                self.face_right = True
            else:
                # if (nose_x > right_shoulder_x) or (nose_x > left_shoulder_x):
                #     print("face right2")
                #     self.face_right = True
                # else:
                self.face_right = False

    def detect_plates(self, frame, min_plate_pct, max_plate_pct, track=False):
        height, width = frame.shape[:2]
        box_x_min = self.min_box_values[0]
        box_x_max = self.max_box_values[0]

        # Testing showed that average barbell plate size roughly between 35-45% of the width of frame
        # Size dependent on distance of squatter from camera
        min_diameter, max_diameter = width * min_plate_pct, width * max_plate_pct
        min_radius, max_radius = int(min_diameter / 2), int(max_diameter / 2)
        min_dist = 2 * min_radius
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_frame = cv2.GaussianBlur(gray_frame, (21, 21), 0)
        circles = cv2.HoughCircles(gray_frame, cv2.HOUGH_GRADIENT, 1, minDist=min_dist,
                                   param1=50, param2=30, minRadius=min_radius, maxRadius=max_radius)
        if circles is not None:
            self.no_circle = 0
            # convert the (x, y) coordinates and radius of the circles to integers
            circles = np.round(circles[0, :]).astype("int")
            for (x, y, r) in circles:
                # If the center of the circle is in the top half of the frame
                if y < height / 2:
                    # If the center of the circle is within the detected person box
                    if box_x_min < x < box_x_max:
                        cv2.circle(frame, (x, y), r, (0, 255, 0), 3)
                        cv2.circle(frame, (x, y), 2, (0, 0, 255), 3)
                        if track:
                            self.barbell_pts.appendleft((x, y))
        else:
            self.no_circle += 1
        # return frame

    def draw_bar_path(self, frame):
        for i in range(1, len(self.barbell_pts)):
            # If either of the tracked points are None, ignore them
            if self.barbell_pts[i - 1] is None or self.barbell_pts[i] is None:
                continue
            # If there has been a big x jump, or no circle detected for 10 frames, empty the queue
            if (self.barbell_pts[i][0] - self.barbell_pts[i - 1][0] > 30) or self.no_circle > 10:
                self.barbell_pts.clear()
                break
            # Compute the thickness of the line and draw the connecting lines
            thickness = int(np.sqrt(self.barbell_pts_len / float(i + 1)) * 1.5)
            cv2.line(frame, self.barbell_pts[i - 1], self.barbell_pts[i], (0, 0, 255), thickness)
        return frame

    def process_video(self, cap, seconds=3):
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_length = frame_count / fps
        print(fps, frame_count, video_length)
        frame_num, prev_time = 0, 0

        # Skip ahead x seconds. Default is 3. Ideally will have the user chose how long they need to setup
        # Can use this to process every x frames too?
        success, frame = cap.read()
        if success:
            if seconds > 0:
                curr_frame = int(fps * seconds)
                skip = True
            else:
                curr_frame = 1
                skip = False
            cap.set(1, curr_frame)
        else:
            cap.release()
            return

        # Determine the orientation of the squatter so that the correct lines can be drawn and values stored
        success, frame = cap.read()
        self.get_orientation(frame)
        # Once orientation has be ascertained, can filter the landmark_connections to only be left or right points
        self.landmark_connections = pl.PoseLandmark(face_right=self.face_right, filter_landmarks=True)
        frame_num = curr_frame + 1
        while True:
            success, frame = cap.read()
            if frame is None:
                break

            # If the user opts not to skip ahead in video (to avoid setup difficulties etc)
            # recheck the orientation every fps frames for 3 seconds
            # Perhaps bin?
            if skip is False:
                if (frame_num < fps * 3) and (frame_num % int(fps) == 0):
                    self.get_orientation(frame)
                    self.landmark_connections = pl.PoseLandmark(face_right=self.face_right, filter_landmarks=True)

            # Resize the frame so less computationally taxing to process. Perhaps make even smaller?
            frame = resize_frame(frame)
            # Utilize mediapipe person detection model to identify landmarks in each frame
            frame = self.find_pose(frame, draw=False, box=True)
            # Store orientation specific landmarks from previous step
            self.find_positions(frame, specific=True)
            # Store frame and pose data into dictionary
            self.pose_data[frame_num] = (frame, self.frame_landmarks)
            # Find relevant joint angles and draw connections
            self.draw_angles(frame_num, reps=True)
            cv2.rectangle(frame, (0, 0), (200, 50), (255, 0, 0), -1)
            cv2.putText(frame, "Reps: " + str(int(self.count)), (10, 30),
                        cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 2)
            # frame = self.detect_plates(frame, 0.35, 0.50)
            # if frame_num % 5 == 0:
            self.detect_plates(frame, 0.35, 0.45, track=True)
            frame = self.draw_bar_path(frame)

            # Pin fps to frame
            prev_time = add_fps(frame, prev_time, frame_num)

            cv2.imshow("Frame", frame)
            frame_num += 1
            key = cv2.waitKey(1)
            if key == 'q' or key == 27:
                break

        while True:
            cv2.imshow("test Frame", self.pose_data[580][0])
            cv2.waitKey(10)
            cv2.imshow("test Frame 2", self.pose_data[150][0])
            cv2.waitKey(10)


def main():
    # cap = cv2.VideoCapture('Videos/GW_BS2.mp4')
    cap = cv2.VideoCapture('Videos/GW_BS3L.mp4')
    # cap = cv2.VideoCapture('Videos/HS_BWS.mp4')
    # cap = cv2.VideoCapture('Videos/AC_BS.mp4')
    # cap = cv2.VideoCapture('Videos/AC_FSL.mp4')
    detector = PoseDetector()
    detector.process_video(cap, 3)


if __name__ == "__main__":
    main()
