import DobotDllType as dType
from config import X_Center, Y_Center, DOBOT_PORT, DOBOT_BAUDRATE

class DobotController:
    def __init__(self):
        self.api = None
        self.CON_STR = {
            dType.DobotConnect.DobotConnect_NoError: "DobotConnect_NoError",
            dType.DobotConnect.DobotConnect_NotFound: "DobotConnect_NotFound",
            dType.DobotConnect.DobotConnect_Occupied: "DobotConnect_Occupied"
        }
        self.state = None
    
    def initialize(self):
        """初始化Dobot連接"""
        # Load Dll
        self.api = dType.load()
        
        # Connect Dobot
        self.state = dType.ConnectDobot(self.api, DOBOT_PORT, DOBOT_BAUDRATE)[0]
        print("Connect status:", self.CON_STR[self.state])
        
        if self.state == dType.DobotConnect.DobotConnect_NoError:
            print("初始化 Dobot 參數")
            dType.SetQueuedCmdClear(self.api)
            dType.SetPTPJointParams(self.api, 200, 200, 200, 200, 200, 200, 200, 200, isQueued=1)
            dType.SetPTPCoordinateParams(self.api, 200, 200, 200, 200, isQueued=1)
            dType.SetPTPCommonParams(self.api, 100, 100, isQueued=1)
            dType.SetHOMECmd(self.api, temp=0, isQueued=1)
            lastIndex = dType.SetWAITCmd(self.api, 2000, isQueued=1)
            self._work(lastIndex)
    
    def _work(self, lastIndex):
        """佇列釋放, 工作執行函數"""
        dType.SetQueuedCmdStartExec(self.api)
        while lastIndex[0] > dType.GetQueuedCmdCurrentIndex(self.api)[0]:
            dType.dSleep(100)
        dType.SetQueuedCmdClear(self.api)
    
    def dobot_work(self, cX, cY, tag_id, hei_z):
        """Dobot 工作函數"""
        if (cY - Y_Center) >= 0:
            offy = (cY - Y_Center) * 0.5001383
        else:
            offy = (cY - Y_Center) * 0.5043755

        if (cX - X_Center) >= 0:
            offx = (X_Center - cX) * 0.4921233
        else:
            offx = (X_Center - cX) * 0.5138767
        obj_x = 268.3032 + offx
        obj_y = offy

        dType.SetEMotor(self.api, 0, 1, 12500, 1)
        dType.SetWAITCmd(self.api, 4850, isQueued=1)
        dType.SetEMotor(self.api, 0, 1, 0, 1)
        dType.SetWAITCmd(self.api, 100, isQueued=1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, obj_x, obj_y, 50, 0, 1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, obj_x, obj_y, hei_z, 0, 1)
        dType.SetEndEffectorSuctionCup(self.api, 1, 1, isQueued=1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, obj_x, obj_y, 70, 0, 1)

        print("color_state = " + str(tag_id))
        if tag_id == "yellow":
            goal_x = 10
            goal_y = 213
        elif tag_id == "blue":
            goal_x = 150
            goal_y = 213
        elif tag_id == "red":
            goal_x = 80
            goal_y = 213
        elif tag_id == "green":
            goal_x = 220
            goal_y = 213

        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, goal_x, -goal_y, 70, 0, 1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, goal_x, -goal_y, 40, 0, 1)
        dType.SetEndEffectorSuctionCup(self.api, 1, 0, isQueued=1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, goal_x, -goal_y, 70, 0, 1)
        dType.SetPTPCmd(self.api, dType.PTPMode.PTPMOVJXYZMode, 270, 0, 50, 0, 1)
        lastIndex = dType.SetWAITCmd(self.api, 100, isQueued=1)
        self._work(lastIndex)
        print("End")
    
    def run_conveyor(self):
        """輸送帶運行函數"""
        dType.SetEMotor(self.api, 0, 1, 12500, 1)
        dType.SetWAITCmd(self.api, 4850, isQueued=1)
        dType.SetEMotor(self.api, 0, 1, 0, 1)
        lastIndex = dType.SetWAITCmd(self.api, 100, isQueued=1)
        self._work(lastIndex)
    
    def disconnect(self):
        """斷開Dobot連接"""
        if self.api:
            dType.SetQueuedCmdStopExec(self.api)
            dType.DisconnectDobot(self.api)