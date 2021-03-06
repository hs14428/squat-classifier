import cv2
import mediapipe as mp
import time
import PoseLandmark as pl


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
    cv2.putText(frame, "fps: " + str(int(fps)), (145, 20), cv2.FONT_HERSHEY_PLAIN, 1.5,
                (255, 0, 0), 1)
    cv2.putText(frame, "Num: " + str(int(frame_num)), (10, 20),
                cv2.FONT_HERSHEY_PLAIN, 1.5, (255, 0, 0), 1)
    return prev_time


class PoseDetector():

    def __init__(self, static_image_mode=False, model_complexity=1, smooth=True,
                 detection_conf=0.5, tracking_conf=0.5):

        self.static_image_mode = static_image_mode
        self.model_complexity = model_complexity
        self.smooth = smooth
        self.detectionConf = detection_conf
        self.trackingConf = tracking_conf

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
        # Custom list for storing all converted landmark data
        self.landmark_list = []
        # Custom dict for storing orientation specific converted landmark data
        self.frame_landmarks = {}
        # Pose dictionary containing relevant frame pose details for analysis
        self.pose_data = {}
        # Sets the orientation of the video
        self.face_right = True

    def find_pose(self, frame, draw=True, box=False):
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.results = self.pose.process(frame_rgb)
        self.landmarks = self.results.pose_landmarks
        pose_connections = self.landmark_connections.POSE_CONNECTIONS
        if self.landmarks:
            if draw:
                self.mpDraw.draw_landmarks(frame, self.landmarks, pose_connections)
            if box:
                min_values, max_values = self.find_box_coordinates(frame)
                cv2.rectangle(frame, min_values, max_values, (0, 255, 0), 2)
        return frame

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

    def find_angles(self, frame_num, p1, p2, p3, draw=True):
        frame = self.pose_data[frame_num][0]
        x1, y1 = self.pose_data[frame_num][1][p1][1:]
        x2, y2 = self.pose_data[frame_num][1][p2][1:]
        x3, y3 = self.pose_data[frame_num][1][p3][1:]

        if draw:
            cv2.line(frame, (x1, y1), (x2, y2), (255, 255, 255), 3)
            cv2.line(frame, (x3, y3), (x2, y2), (255, 255, 255), 3)
            cv2.circle(frame, (x1, y1), 10, (0, 255, 0), cv2.FILLED)
            cv2.circle(frame, (x1, y1), 15, (0, 255, 0), 2)
            cv2.circle(frame, (x2, y2), 10, (0, 255, 0), cv2.FILLED)
            cv2.circle(frame, (x2, y2), 15, (0, 255, 0), 2)
            cv2.circle(frame, (x3, y3), 10, (0, 255, 0), cv2.FILLED)
            cv2.circle(frame, (x3, y3), 15, (0, 255, 0), 2)

    def draw_connections(self, frame, frame_num):
        p1, p2, p3 = self.landmark_connections.HIP_ANGLE_CONNECTIONS
        self.find_angles(frame_num, p1, p2, p3, draw=True)
        p1, p2, p3 = self.landmark_connections.KNEE_ANGLE_CONNECTIONS
        self.find_angles(frame_num, p1, p2, p3, draw=True)

    # Determine whether squatter is facing left or right. Default is right
    def get_orientation(self, frame):
        self.find_pose(frame, draw=False)
        self.find_positions(frame)
        # Extract x values for the shoulders and nose to compare
        right_shoulder_x = self.landmark_list[self.landmark_connections.RIGHT_SHOULDER][1]
        left_shoulder_x = self.landmark_list[self.landmark_connections.LEFT_SHOULDER][1]
        nose_x = self.landmark_list[self.landmark_connections.NOSE][1]
        # If the nose is further along the x axis than either shoulders, facing right
        if (nose_x > right_shoulder_x) or (nose_x > left_shoulder_x):
            self.face_right = True
        else:
            self.face_right = False

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
            curr_frame = int(fps * seconds)
            cap.set(1, curr_frame)
        else:
            cap.release()
            return
        print(curr_frame)
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

            # Resize the frame so less computationally taxing to process
            frame = resize_frame(frame)
            # Utilize mediapipe person detection model to identify landmarks in each frame
            frame = self.find_pose(frame, draw=False, box=True)
            # Store orientation specific landmarks from previous step
            self.find_positions(frame, specific=True)
            # Store frame and pose data into dictionary
            self.pose_data[frame_num] = (frame, self.frame_landmarks)
            # Find relevant joint angles and draw connections
            self.draw_connections(frame, frame_num)

            # Pin fps to frame
            prev_time = add_fps(frame, prev_time, frame_num)

            # if frame_num == 91:
            #     frame_test = self.pose_data[91][0]
            #     print(self.pose_data[91][0])
            #     cv2.imshow("Test", frame_test)
            #     cv2.waitKey(1)
            #     print(self.pose_data[91][1][self.landmark_connections.LEFT_SHOULDER][1])
            #     break
            cv2.imshow("Frame", frame)
            frame_num += 1
            key = cv2.waitKey(1)
            if key == 'q' or key == 27:
                break


def main():
    cap = cv2.VideoCapture('Videos/GW_BS2.mp4')
    # cap = cv2.VideoCapture('Videos/HS_BWS.mp4')
    # cap = cv2.VideoCapture('Videos/AC_BS.mp4')
    detector = PoseDetector()
    detector.process_video(cap, 3)


if __name__ == "__main__":
    main()
