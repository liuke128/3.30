import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, 
                            QGroupBox, QFrame, QGridLayout, QDialog, QScrollArea)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import fsolve
import pandas as pd

class StatusLight(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet("background-color: red; border-radius: 10px;")
        
    def set_status(self, status):
        color = "green" if status else "red"
        self.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

class ImageViewerDialog(QDialog):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片查看")
        self.setWindowFlags(Qt.Window | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        
        # 获取屏幕尺寸
        screen = QApplication.primaryScreen().geometry()
        self.setMinimumSize(screen.width() // 2, screen.height() // 2)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建图片容器
        self.image_container = QWidget()
        self.image_container.setStyleSheet("background-color: white;")
        container_layout = QVBoxLayout(self.image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # 创建图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.image_label)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidget(self.image_container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        # 添加关闭按钮
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 5, 10, 5)
        close_button = QPushButton("关闭")
        close_button.setFixedWidth(100)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #dcdcdc;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #e6e6e6;
            }
        """)
        close_button.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 保存原始图片
        self.original_pixmap = pixmap
        # 初始显示
        self.resizeEvent(None)
    
    def resizeEvent(self, event):
        """当窗口大小改变时，调整图片大小"""
        if hasattr(self, 'original_pixmap') and not self.original_pixmap.isNull():
            # 获取可用空间大小（减去按钮区域高度）
            available_size = self.size()
            available_size.setHeight(available_size.height() - 40)  # 40是按钮区域的高度
            
            # 计算缩放后的图片大小
            scaled_pixmap = self.original_pixmap.scaled(
                available_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # 更新图片
            self.image_label.setPixmap(scaled_pixmap)

class ClickableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)  # 设置鼠标指针为手型
        
    def mouseDoubleClickEvent(self, event):
        if self.pixmap() and not self.pixmap().isNull():
            dialog = ImageViewerDialog(self.pixmap(), self.window())
            dialog.exec_()

class ThermoelectricCalculator:
    def __init__(self):
        # 移除对iter_edit的依赖
        self.p_type_data = {}
        self.n_type_data = {}
        self.interpolators = {}
        
        # 读取P型材料数据，修正组分值对应关系
        p_files = {
            "0.01": "P_yuanshi_2_5.xls",  # 0.01对应2.5
            "0.02": "P_yuanshi_3_1.xls",  # 0.02对应3.1
            "0.03": "P_yuanshi_3_7.xls"   # 0.03对应3.7
        }
        
        # 读取N型材料数据
        n_files = {
            "0.0004": "N_yuanshi_0.0004.xls",
            "0.0012": "N_yuanshi_0.0012.xls",
            "0.0020": "N_yuanshi_0.0020.xls",
            "0.0028": "N_yuanshi_0.0028.xls"
        }
        
        def read_excel_file(filename):
            """读取Excel文件的辅助函数"""
            try:
                # 首先尝试使用xlrd引擎
                try:
                    import xlrd
                    # 不使用列名读取数据
                    data = pd.read_excel(filename, engine='xlrd', header=None)
                    print(f"成功使用xlrd读取文件: {filename}")
                    return data
                except ImportError:
                    print("xlrd未安装，尝试使用openpyxl...")
                    return None
            except Exception as e:
                print(f"读取文件失败: {str(e)}")
                return None
        
        def find_columns(data):
            """根据数据结构查找相应的列"""
            try:
                # 检查数据的结构来确定正确的列索引
                # 对于P_yuanshi文件（如P_yuanshi_2_5.xls），列结构为：
                # 温度(A列,0), 塞贝克系数(B列,1), 温度(C列,2), 电阻率(D列,3), 温度(E列,4), 优值系数(F列,5)
                if data.shape[1] >= 6:  # 确保有足够的列
                    print("找到的列结构：")
                    for i in range(min(6, data.shape[1])):
                        print(f"列 {i}: {data.iloc[0, i]}")
                    
                    # 检查前几行的数据来识别是P型还是N型文件
                    # P型文件特征：第一列数值在300左右（温度）
                    first_col_values = data.iloc[0:5, 0].values
                    print(f"第一列前5个值: {first_col_values}")
                    
                    if any(290 <= v <= 310 for v in first_col_values if isinstance(v, (int, float))):
                        print("检测到P型材料数据文件格式")
                        return {
                            "temp": 0,        # A列作为温度
                            "seebeck": 1,     # B列作为塞贝克系数
                            "resistivity": 3, # D列作为电阻率
                            "thermal_cond": 5 # F列作为优值系数（但我们需要另外计算热导率）
                        }
                    else:
                        print("检测到N型材料数据文件格式")
                        return {
                            "temp": 0,        # 第1列作为温度
                            "seebeck": 1,     # 第2列作为塞贝克系数
                            "resistivity": 3, # 第4列作为电阻率
                            "thermal_cond": 5 # 第6列作为热导率
                        }
                else:
                    print("警告：数据列数不足，使用默认列映射")
                    return {
                        "temp": 0,
                        "seebeck": 1,
                        "resistivity": 3,
                        "thermal_cond": 5
                    }
            except Exception as e:
                print(f"查找列错误: {str(e)}")
                import traceback
                traceback.print_exc()
                return None
        
        # 读取所有P型材料数据
        for composition, filename in p_files.items():
            print(f"\n尝试读取P型材料数据文件: {filename}")
            data = read_excel_file(filename)
            if data is not None:
                try:
                    # 查找列
                    columns = find_columns(data)
                    if columns:
                        # P型材料：F列是优值系数(ZT)，我们需要从中反推热导率
                        # 热导率 k = (α^2 × T) / (ρ × ZT)
                        # 其中 α 是塞贝克系数，ρ 是电阻率，T 是温度，ZT 是优值系数
                        seebeck = data[columns['seebeck']].values * 1e-6  # μV/K 转换为 V/K
                        resistivity = data[columns['resistivity']].values * 1e-6  # μΩ·m 转换为 Ω·m (修正单位换算错误)
                        temperature = data[columns['temp']].values
                        zt_values = data[columns['thermal_cond']].values  # 这里实际上是ZT值
                        
                        # 计算热导率
                        thermal_cond = []
                        for i in range(len(temperature)):
                            try:
                                # 避免无效ZT值和除以零
                                if zt_values[i] > 0:
                                    # 修正电阻率单位 (正确系数1e-6)
                                    k = (seebeck[i]**2 * temperature[i]) / (resistivity[i] * zt_values[i])
                                    thermal_cond.append(k)
                                else:
                                    thermal_cond.append(2.0)  # 更合理的默认值
                            except:
                                thermal_cond.append(2.0)  # 更合理的默认值
                        
                        self.p_type_data[composition] = {
                            "temp": temperature,
                            "seebeck": seebeck,
                            "resistivity": resistivity,  # 已经在之前的部分用1e-6修正过
                            "thermal_cond": np.array(thermal_cond)  # 从ZT反推的热导率
                        }
                        print(f"成功读取P型材料数据: {composition}")
                        print(f"温度范围: {min(temperature)}-{max(temperature)} K")
                        print(f"塞贝克系数范围: {min(seebeck*1e6)}-{max(seebeck*1e6)} μV/K")
                        print(f"电阻率范围: {min(resistivity*1e6)}-{max(resistivity*1e6)} μΩ·m")
                        print(f"计算的热导率范围: {min(thermal_cond)}-{max(thermal_cond)} W/(m·K)")
                    else:
                        print(f"在文件 {filename} 中未找到所需的列")
                        
                except Exception as e:
                    print(f"处理P型材料数据文件 {filename} 时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
        
        # 读取所有N型材料数据
        for composition, filename in n_files.items():
            print(f"\n尝试读取N型材料数据文件: {filename}")
            data = read_excel_file(filename)
            if data is not None:
                try:
                    # 查找列
                    columns = find_columns(data)
                    if columns:
                        self.n_type_data[composition] = {
                            "temp": data[columns['temp']].values,
                            "seebeck": -data[columns['seebeck']].values * 1e-6,  # μV/K 转换为 V/K，N型为负值
                            "resistivity": data[columns['resistivity']].values * 1e-5,  # μΩ·m 转换为 Ω·m
                            "thermal_cond": data[columns['thermal_cond']].values  # W/(m·K)
                        }
                        print(f"成功读取N型材料数据: {composition}")
                    else:
                        print(f"在文件 {filename} 中未找到所需的列")
                        
                except Exception as e:
                    print(f"处理N型材料数据文件 {filename} 时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    
        print("\n数据读取完成")
        print(f"成功读取的P型材料: {list(self.p_type_data.keys())}")
        print(f"成功读取的N型材料: {list(self.n_type_data.keys())}")
        
    def create_interpolators(self, material_type, composition):
        """为给定材料创建属性插值器"""
        try:
            data = self.p_type_data if material_type == 'p' else self.n_type_data
            mat_data = data[composition]
            
            # ==== 增加插值范围限制 ====
            temps = mat_data["temp"]
            seebeck = mat_data["seebeck"]
            resistivity = mat_data["resistivity"]
            thermal_cond = mat_data["thermal_cond"]
            
            # 确保数据有序
            sort_idx = np.argsort(temps)
            temps = temps[sort_idx]
            seebeck = seebeck[sort_idx]
            resistivity = resistivity[sort_idx]
            thermal_cond = thermal_cond[sort_idx]
            
            # 打印材料属性范围
            print(f"\n===== 创建 {material_type}型材料插值器 (组分={composition}) =====")
            print(f"温度范围: {min(temps)}-{max(temps)} K")
            print(f"塞贝克系数范围: {min(seebeck*1e6):.2f}-{max(seebeck*1e6):.2f} μV/K")
            print(f"电阻率范围: {min(resistivity*1e6):.2f}-{max(resistivity*1e6):.2f} μΩ·m")
            print(f"热导率范围: {min(thermal_cond):.2f}-{max(thermal_cond):.2f} W/(m·K)")
            
            # 创建边界值保护的插值器
            self.interpolators[f"{material_type}_{composition}"] = {
                "seebeck": interp1d(temps, seebeck, kind='linear', 
                                   bounds_error=False, 
                                   fill_value=(seebeck[0], seebeck[-1])),  # 限制外推值
                "resistivity": interp1d(temps, resistivity, kind='linear',
                                      bounds_error=False,
                                      fill_value=(resistivity[0], resistivity[-1])),
                "thermal_cond": interp1d(temps, thermal_cond, kind='linear',
                                       bounds_error=False,
                                       fill_value=(thermal_cond[0], thermal_cond[-1]))
            }
            
            print(f"插值器创建成功")
            
        except Exception as e:
            print(f"创建插值器错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def calculate_temperature_distribution(self, Th, Tc, n_points, material_type, composition, current_density, max_iter=50):
        """
        根据参考算法计算温度分布
        """
        try:
            print(f"\n开始计算温度分布: {material_type}型, 组分={composition}, 电流密度={current_density}A/cm²")
            print(f"边界条件: Th={Th}K, Tc={Tc}K, 格点数={n_points}")
            
            # 创建插值器（如果还没有创建）
            interp_key = f"{material_type}_{composition}"
            if interp_key not in self.interpolators:
                self.create_interpolators(material_type, composition)
            
            # 初始化格点位置和温度
            L = 1.0  # 标准化长度
            dx = L / (n_points - 1)  # 网格间距
            x = np.linspace(0, L, n_points)  # 从0到1的均匀分布
            T = np.linspace(Tc, Th, n_points)  # 初始线性温度分布
            
            print(f"初始温度分布: {T}")
            
            # 电流密度转换为A/m²
            J = current_density * 100  # A/cm² → A/m²
            
            # 开始迭代
            for iter_count in range(max_iter):
                # 计算各节点处的材料属性
                seebeck = np.zeros(n_points)
                resistivity = np.zeros(n_points)
                thermal_cond = np.zeros(n_points)
                
                for i in range(n_points):
                    T_safe = np.clip(T[i], 300, 700)  # 确保温度在有效范围内
                    seebeck[i] = self.interpolators[interp_key]["seebeck"](T_safe)
                    resistivity[i] = self.interpolators[interp_key]["resistivity"](T_safe)
                    thermal_cond[i] = self.interpolators[interp_key]["thermal_cond"](T_safe)
                
                # 计算参考算法中的系数
                c1 = J * seebeck / thermal_cond
                c2 = -1 / thermal_cond
                c3 = seebeck**2 * J**2 / thermal_cond
                c4 = -J * seebeck / thermal_cond
                c5 = resistivity * J**2
                
                # 构建系数矩阵和右端向量
                A = np.zeros((n_points, n_points))
                b = np.zeros(n_points)
                
                # 设置边界条件
                A[0, 0] = 1.0
                b[0] = Tc
                A[n_points-1, n_points-1] = 1.0
                b[n_points-1] = Th
                
                # 构造内部点的系数矩阵，使用与参考算法一致的形式
                for i in range(1, n_points-1):
                    A[i, i-1] = 1 / (c2[i] * dx)
                    A[i, i] = c4[i+1] / c2[i+1] - 1 / (c2[i+1] * dx) - (1 - c1[i] * dx) / (c2[i] * dx)
                    A[i, i+1] = (1 - c1[i+1] * dx) / (c2[i+1] * dx) - c3[i+1] * dx - (1 - c1[i+1] * dx) * c4[i+1] / c2[i+1]
                    b[i] = c5[i-1] * dx
                
                # 尝试求解线性方程组
                try:
                    T_new = np.linalg.solve(A, b)
                    
                    # 检查解的合理性
                    if np.any(np.isnan(T_new)) or np.any(np.isinf(T_new)):
                        print(f"警告：第{iter_count+1}次迭代解不合理，使用线性插值")
                        T_new = np.linspace(Tc, Th, n_points)
                    
                    # 限制温度在物理合理范围内
                    T_new = np.clip(T_new, min(Tc, Th)*0.95, max(Tc, Th)*1.1)
                    
                    # 计算收敛情况
                    max_change = np.max(np.abs(T_new - T))
                    print(f"迭代{iter_count+1}次完成，最大温度变化: {max_change:.6f}K")
                    
                    # 更新温度
                    T = T_new.copy()
                    
                    # 判断是否已经收敛
                    if max_change < 0.01:  # 收敛阈值
                        print(f"温度分布已收敛，在第{iter_count+1}次迭代")
                        break
                        
                except np.linalg.LinAlgError:
                    print(f"警告：线性方程组求解失败，使用线性温度分布")
                    T = np.linspace(Tc, Th, n_points)
                    break
            
            # 打印最终温度分布
            print(f"最终温度分布: {T}")
            
            return x, T
            
        except Exception as e:
            print(f"计算温度分布错误: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 出错时返回线性温度分布
            L = 1.0
            return np.linspace(0, L, n_points), np.linspace(Tc, Th, n_points)
    
    def calculate_efficiency(self, Th, Tc, material_type, composition, current_density, x=None, T=None):
        """
        根据参考算法计算热电材料效率
        
        参数:
        Th: 高温端温度 (K)
        Tc: 低温端温度 (K)
        material_type: 材料类型 ('p' 或 'n')
        composition: 材料组分
        current_density: 电流密度 (A/cm²)
        x, T: 温度分布数据
        
        返回:
        efficiency: 效率 (%)
        power: 输出功率密度 (W/m²)
        """
        try:
            # 验证输入参数
            if Th <= Tc:
                print(f"警告: 温度差无效 (Th={Th}K, Tc={Tc}K)")
                return 0.0, 0.0
                
            # 准备插值器
            interp_key = f"{material_type}_{composition}"
            if interp_key not in self.interpolators:
                self.create_interpolators(material_type, composition)
                
            # 确保温度分布数据有效
            if x is None or T is None or len(x) < 3:
                print(f"温度分布数据无效，使用线性温度分布近似")
                n_points = 20
                x = np.linspace(0, 1.0, n_points)
                T = np.linspace(Tc, Th, n_points)
                
            # 获取格点数和间距
            n_points = len(x)
            dx = (x[-1] - x[0]) / (n_points - 1)
            
            # 获取材料属性
            seebeck = np.zeros(n_points)
            resistivity = np.zeros(n_points)
            thermal_cond = np.zeros(n_points)
            
            for i in range(n_points):
                T_safe = np.clip(T[i], 300, 700)  # 确保温度在有效范围内
                seebeck[i] = self.interpolators[interp_key]["seebeck"](T_safe)
                resistivity[i] = self.interpolators[interp_key]["resistivity"](T_safe)
                thermal_cond[i] = self.interpolators[interp_key]["thermal_cond"](T_safe)
                
            # 电流密度转换为SI单位: A/cm² → A/m²
            J = current_density * 10000  # 转换为A/m²
            
            # 计算参考算法中的系数
            c1 = J * seebeck / thermal_cond
            c2 = -1 / thermal_cond
            c3 = seebeck**2 * J**2 / thermal_cond
            c4 = -J * seebeck / thermal_cond
            c5 = resistivity * J**2
            
            # 计算热流密度 q
            q = np.zeros(n_points)
            for k in range(1, n_points):
                q[k] = ((1/dx - c1[k]) * T[k] - T[k-1]/dx) / c2[k]
            # 边界热流计算
            q[0] = (1 - c4[1] * dx) * q[1] - c3[1] * dx * T[1] - c5[1] * dx
            
            # 计算积分项
            cumulative_seebeck = 0  # 塞贝克积分项
            cumulative_resistivity = 0  # 电阻率积分项
            
            for m in range(1, n_points):
                T1 = T[m]
                T2 = T[m-1]
                # 使用梯形法则进行积分
                avg_seebeck = (seebeck[m] + seebeck[m-1]) / 2
                avg_resistivity = (resistivity[m] + resistivity[m-1]) / 2
                
                cumulative_seebeck += avg_seebeck * (T1 - T2)
                cumulative_resistivity += avg_resistivity * dx
            
            # 计算效率
            if q[n_points-1] != 0:
                efficiency = J * (cumulative_seebeck + J * cumulative_resistivity) / q[n_points-1] * 100  # 转为百分比
                
                # 检查是否为有效值
                if efficiency < 0:
                    print(f"计算得到负效率 ({efficiency:.4f}%), 设为0")
                    efficiency = 0.0
                    
                # 验证效率是否超过卡诺效率
                carnot_eff = (Th - Tc) / Th * 100
                if efficiency > carnot_eff:
                    print(f"警告: 计算效率 {efficiency:.4f}% 超过卡诺效率 {carnot_eff:.4f}%")
                    efficiency = carnot_eff * 0.9  # 限制在卡诺效率的90%以内
            else:
                print("热流为零，无法计算效率")
                efficiency = 0.0
                
            # 计算功率
            power = J * (cumulative_seebeck + J * cumulative_resistivity)
            
            print(f"材料: {material_type}型, 组分={composition}, 电流密度={current_density}A/cm², 效率={efficiency:.4f}%")
            return efficiency, power
            
        except Exception as e:
            print(f"效率计算错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0.0, 0.0

    def calculate_zt(self, material_type, composition, temperature):
        """计算给定温度下的优值系数 ZT = S²T/(kρ)
        
        参数:
        material_type: 'p' 或 'n'，材料类型
        composition: 材料成分
        temperature: 温度 (K)
        
        返回:
        zt: 优值系数
        """
        try:
            # 创建插值器（如果还没有创建）
            interp_key = f"{material_type}_{composition}"
            if interp_key not in self.interpolators:
                self.create_interpolators(material_type, composition)
            
            # 获取材料属性
            # 塞贝克系数 (V/K)，使用绝对值因为N型材料的塞贝克系数为负
            seebeck = abs(self.interpolators[interp_key]["seebeck"](temperature))
            # 电阻率 (Ω·m)
            resistivity = self.interpolators[interp_key]["resistivity"](temperature)
            # 热导率 (W/(m·K))
            thermal_cond = self.interpolators[interp_key]["thermal_cond"](temperature)
            
            # 计算优值系数 ZT = S²T/(kρ)
            # S: 塞贝克系数 (V/K)
            # T: 温度 (K)
            # k: 热导率 (W/(m·K))
            # ρ: 电阻率 (Ω·m)
            zt = (seebeck ** 2) * temperature / (thermal_cond * resistivity)
            
            return zt
            
        except Exception as e:
            print(f"计算优值系数错误: {str(e)}")
            return 0

    def visualize_energy_flow(self, material_type, composition, current_density, x, T):
        """
        可视化材料内部的能量流动
        """
        try:
            # 创建图表
            fig, axes = plt.subplots(2, 1, figsize=(8, 10))
            fig.suptitle(f"{material_type}型材料 (组分={composition}) 能量流分析", fontsize=14)
            
            # 转换单位
            J = current_density * 1e4  # A/cm² → A/m²
            
            # 准备数据
            n_points = len(x)
            dx = (x[-1] - x[0]) / (n_points - 1)
            
            # 计算温度梯度
            dTdx = np.zeros_like(T)
            dTdx[1:-1] = (T[2:] - T[:-2]) / (2*dx)
            dTdx[0] = (T[1] - T[0]) / dx
            dTdx[-1] = (T[-1] - T[-2]) / dx
            
            # 获取材料属性
            interp_key = f"{material_type}_{composition}"
            seebeck = np.zeros(n_points)
            resistivity = np.zeros(n_points)
            thermal_cond = np.zeros(n_points)
            
            for i in range(n_points):
                T_safe = np.clip(T[i], 300, 700)
                seebeck[i] = self.interpolators[interp_key]["seebeck"](T_safe)
                resistivity[i] = self.interpolators[interp_key]["resistivity"](T_safe)
                thermal_cond[i] = self.interpolators[interp_key]["thermal_cond"](T_safe)
            
            # 计算各种热流密度
            fourier_heat = thermal_cond * dTdx              # 傅里叶热流 κ·dT/dx
            peltier_heat = J * seebeck * T                  # 帕尔贴热流 J·S·T
            total_heat = fourier_heat - peltier_heat        # 净热流 q = κ·dT/dx - J·S·T
            joule_heat = J**2 * resistivity                 # 焦耳热 J²·ρ
            seebeck_power = J * seebeck * dTdx              # 塞贝克功率 J·S·dT/dx
            
            # 绘制热流分布
            ax1 = axes[0]
            ax1.plot(x, fourier_heat, 'r-', label='傅里叶热流 (κ·dT/dx)')
            ax1.plot(x, peltier_heat, 'b-', label='帕尔贴热流 (J·S·T)')
            ax1.plot(x, total_heat, 'g-', label='净热流 (q)')
            ax1.set_xlabel('位置 (归一化)')
            ax1.set_ylabel('热流密度 (W/m²)')
            ax1.legend()
            ax1.grid(True)
            
            # 绘制功率和热损失
            ax2 = axes[1]
            ax2.plot(x, seebeck_power, 'b-', label='塞贝克功率 (J·S·dT/dx)')
            ax2.plot(x, joule_heat, 'r-', label='焦耳热损失 (J²·ρ)')
            ax2.plot(x, seebeck_power - joule_heat, 'g-', label='净功率')
            ax2.set_xlabel('位置 (归一化)')
            ax2.set_ylabel('功率密度 (W/m³)')
            ax2.legend()
            ax2.grid(True)
            
            # 显示图表
            plt.tight_layout()
            plt.show()
            
        except Exception as e:
            print(f"能量流可视化错误: {str(e)}")
            import traceback
            traceback.print_exc()

class ThermoelectricApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setup_plot_style()
        self.setWindowTitle('基于差分法的半导体热电器件仿真实验')
        
        # 设置窗口的默认大小和最小大小
        screen = QApplication.primaryScreen().geometry()
        default_width = min(int(screen.width() * 0.8), 1440)  # 最大宽度1440
        default_height = min(int(screen.height() * 0.8), 900)  # 最大高度900
        self.setGeometry(100, 100, default_width, default_height)
        self.setMinimumSize(1024, 600)  # 设置最小窗口大小
        
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建主布局
        main_layout = QHBoxLayout(main_widget)
        main_layout.setSpacing(5)  # 减小面板之间的间距
        main_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        
        # 创建左侧面板 - 先创建它，确保iter_edit已经定义
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel)
        
        # 初始化计算器 - 现在iter_edit已经存在
        self.calculator = ThermoelectricCalculator()
        
        # 创建中间面板
        middle_panel = self.create_middle_panel()
        main_layout.addWidget(middle_panel)
        
        # 创建右侧面板
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel)
        
        # 设置面板的比例 (左:中:右 = 2:3:3)
        main_layout.setStretch(0, 2)
        main_layout.setStretch(1, 3)
        main_layout.setStretch(2, 3)

        # 连接信号和槽
        self.init_button.clicked.connect(self.initialize_calculation)
        self.p_current_combo.currentTextChanged.connect(self.update_branch_characteristics)
        self.n_current_combo.currentTextChanged.connect(self.update_branch_characteristics)
        self.p_type_combo.currentIndexChanged.connect(self.update_p_current_range)
        
        # 连接右侧面板的计算和导出按钮
        self.right_calc_button.clicked.connect(self.calculate_device_performance)
        self.right_export_button.clicked.connect(self.export_data)

    def setup_plot_style(self):
        plt.style.use('default')
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
        plt.rcParams['axes.unicode_minus'] = False     # 用来正常显示负号
        
        plt.rcParams.update({
            'figure.facecolor': '#F0F0F0',
            'axes.facecolor': '#F0F0F0',
            'axes.grid': False,
            'axes.spines.top': True,
            'axes.spines.right': True,
            'font.size': 10,
            'figure.subplot.hspace': 0.3,
            'figure.subplot.wspace': 0.3
        })

    def create_toolbar_buttons(self):
        buttons = []
        icons = ["⌂", "←", "→", "✥", "🔍", "≡", "📄"]
        for icon in icons:
            btn = QPushButton(icon)
            btn.setFixedSize(25, 25)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 1px solid #CCCCCC;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #E6E6E6;
                }
            """)
            buttons.append(btn)
        return buttons

    def create_plot_widget(self, num_subplots=2, height=3, vertical=False):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)  # 完全移除边距
        layout.setSpacing(0)  # 移除间距
        
        # 创建工具栏
        toolbar = QFrame()
        toolbar.setFixedHeight(16)  # 进一步减小工具栏高度
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #F0F0F0;
                border: none;
                margin: 0px;
                padding: 0px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(1, 0, 1, 0)  # 只保留左右边距
        toolbar_layout.setSpacing(1)  # 最小按钮间距
        
        # 创建工具按钮
        icons = ["⌂", "←", "→", "+", "🔍", "≡", "📄"]
        for icon in icons:
            btn = QPushButton(icon)
            btn.setFixedSize(16, 16)  # 进一步减小按钮大小
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 1px solid #CCCCCC;
                    border-radius: 1px;
                    padding: 0px;
                    margin: 0px;
                    font-size: 9px;
                }
                QPushButton:hover {
                    background-color: #E6E6E6;
                }
            """)
            toolbar_layout.addWidget(btn)
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)
        
        # 创建图表
        dpi = QApplication.primaryScreen().logicalDotsPerInch()
        fig_width = container.width() / dpi
        fig_height = (height * 96 + 10) / dpi  # 稍微增加图表高度
        
        if vertical and num_subplots > 1:
            fig, axes = plt.subplots(num_subplots, 1, figsize=(fig_width, fig_height))
        else:
            fig, axes = plt.subplots(1, num_subplots, figsize=(fig_width, fig_height))
        
        if num_subplots == 1:
            axes = [axes]
        
        # 设置图表样式
        for ax in axes:
            ax.grid(True, color='white', linestyle='-', alpha=0.8)
            ax.set_facecolor('#F0F0F0')
            ax.clear()
            ax.grid(True)
            # 调整字体大小
            ax.tick_params(labelsize=8)
            for label in ax.get_xticklabels() + ax.get_yticklabels():
                label.set_fontsize(8)
        
        # 调整图表间距，进一步减小上边距
        plt.subplots_adjust(top=0.88, bottom=0.15, left=0.15, right=0.95)
        
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        return container, axes, canvas

    def create_left_panel(self):
        panel = QGroupBox()
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 添加标题
        title_label = QLabel("基于差分法的半导体热电器件仿真实验")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #0072BC;
            padding: 5px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setFixedHeight(50)
        layout.addWidget(title_label)
        
        # 添加示意图
        image_container = QGroupBox()
        image_layout = QVBoxLayout(image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        
        # 使用新的ClickableImageLabel替代QLabel
        image_label = ClickableImageLabel()
        pixmap = QPixmap("图片1.png")
        scaled_pixmap = pixmap.scaled(400, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image_label.setPixmap(scaled_pixmap)
        image_label.setAlignment(Qt.AlignCenter)
        # 添加提示文本
        image_label.setToolTip("双击查看大图")
        image_layout.addWidget(image_label)
        
        layout.addWidget(image_container)
        layout.addSpacing(10)
        
        # 初始条件设置
        params_group = QGroupBox("初始条件设置")
        params_layout = QGridLayout()
        params_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        params_layout.setSpacing(5)  # 减小间距
        
        # 温度和网格设置
        params_layout.addWidget(QLabel("高温温度Th(K)"), 0, 0)
        self.th_edit = QLineEdit("500")
        params_layout.addWidget(self.th_edit, 0, 1)
        
        params_layout.addWidget(QLabel("格子数量"), 0, 2)
        self.grid_edit = QLineEdit("10")
        params_layout.addWidget(self.grid_edit, 0, 3)
        
        params_layout.addWidget(QLabel("低温温度Tc(K)"), 1, 0)
        self.tc_edit = QLineEdit("300")
        params_layout.addWidget(self.tc_edit, 1, 1)
        
        params_layout.addWidget(QLabel("迭代次数"), 1, 2)
        self.iter_edit = QLineEdit("20")
        params_layout.addWidget(self.iter_edit, 1, 3)
        
        # 材料选择
        params_layout.addWidget(QLabel("PbTe1-yIy"), 2, 0)
        self.p_type_combo = QComboBox()
        self.p_type_combo.addItems(["0.01", "0.02", "0.03"])  # 更新P型材料选项为正确的组分值
        params_layout.addWidget(self.p_type_combo, 2, 1)
        
        params_layout.addWidget(QLabel("PbTe:Na/Ag2Te"), 2, 2)
        self.n_type_combo = QComboBox()
        self.n_type_combo.addItems(["0.0004", "0.0012", "0.0020", "0.0028"])  # 更新N型材料选项
        params_layout.addWidget(self.n_type_combo, 2, 3)
        
        params_group.setLayout(params_layout)
        layout.addWidget(params_group)
        
        # 材料优值系数图表
        zt_group = QGroupBox("选择材料的优值系数")
        zt_layout = QVBoxLayout()
        zt_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        
        zt_container, (ax1, ax2), canvas = self.create_plot_widget(height=2)
        self.zt_axes = (ax1, ax2)  # 保存axes引用以便后续更新
        self.zt_canvas = canvas    # 保存canvas引用以便后续更新
        
        # 设置P型图表
        ax1.set_title("P型半导体材料", pad=5)
        ax1.set_xlabel("温度")
        ax1.set_ylabel("ZT")
        ax1.set_xlim(300, 700)
        ax1.set_ylim(0, 1.5)
        ax1.grid(True, color='white', linestyle='-', alpha=0.8)
        ax1.set_facecolor('#F0F0F0')
        
        # 设置N型图表
        ax2.set_title("N型半导体材料", pad=5)
        ax2.set_xlabel("温度")
        ax2.set_ylabel("ZT")
        ax2.set_xlim(300, 700)
        ax2.set_ylim(0, 1.5)
        ax2.grid(True, color='white', linestyle='-', alpha=0.8)
        ax2.set_facecolor('#F0F0F0')
        
        # 调整图表布局
        plt.tight_layout()
        
        zt_layout.addWidget(zt_container)
        zt_group.setLayout(zt_layout)
        layout.addWidget(zt_group)
        
        # 添加初始化按钮和状态指示灯
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(5, 0, 5, 5)  # 减小边距
        self.init_button = QPushButton("初始化运算")
        button_layout.addWidget(self.init_button)
        
        button_layout.addWidget(QLabel("运行状态"))
        self.status_light = StatusLight()
        button_layout.addWidget(self.status_light)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 设置拉伸因子，使图片区域占据更多空间
        layout.setStretch(0, 1)  # 标题
        layout.setStretch(1, 4)  # 图片
        layout.setStretch(2, 0)  # 间距
        layout.setStretch(3, 2)  # 参数设置
        layout.setStretch(4, 2)  # 优值系数图表
        
        panel.setLayout(layout)
        return panel

    def create_middle_panel(self):
        panel = QGroupBox("分支特性")
        layout = QVBoxLayout()
        
        # 格点温度分布
        temp_group = QGroupBox("格点温度分布")
        temp_layout = QVBoxLayout()
        
        temp_container, (ax1, ax2), canvas = self.create_plot_widget()
        # 保存温度分布图表的引用
        self.temp_axes = (ax1, ax2)
        self.temp_canvas = canvas
        
        # 移除多余的提示标签
        
        ax1.set_title("格点温度分布（P型）")
        ax2.set_title("格点温度分布（N型）")
        
        for ax in [ax1, ax2]:
            ax.set_xlabel("格点位置")
            ax.set_ylabel("T (K)")
            ax.set_xlim(0, 10)
            ax.set_ylim(300, 500)
        
        temp_layout.addWidget(temp_container)
        
        # 电流密度选择
        current_layout = QHBoxLayout()
        current_layout.addWidget(QLabel("电流密度（A/cm2）"))
        self.p_current_combo = QComboBox()
        self.p_current_combo.addItems(["-2.0", "-1.5", "-1.0", "-0.5"])
        current_layout.addWidget(self.p_current_combo)
        
        current_layout.addWidget(QLabel("电流密度（A/cm2）"))
        self.n_current_combo = QComboBox()
        self.n_current_combo.addItems(["25", "30", "35", "40"])
        current_layout.addWidget(self.n_current_combo)
        
        temp_layout.addLayout(current_layout)
        temp_group.setLayout(temp_layout)
        layout.addWidget(temp_group)
        
        # 材料效率
        eff_group = QGroupBox("材料效率")
        eff_layout = QVBoxLayout()
        
        eff_container, (ax3, ax4), canvas = self.create_plot_widget()
        # 保存效率图表的引用
        self.eff_axes = (ax3, ax4)
        self.eff_canvas = canvas
        
        ax3.set_title("效率（P型）")
        ax4.set_title("效率（N型）")
        
        ax3.set_xlabel("电流密度(A/cm2)")
        ax3.set_ylabel("效率")
        ax3.set_xlim(-20, 0)
        ax3.set_ylim(0, 0.1)
        
        ax4.set_xlabel("电流密度(A/cm2)")
        ax4.set_ylabel("效率")
        ax4.set_xlim(0, 50)
        ax4.set_ylim(0, 0.1)
        
        eff_layout.addWidget(eff_container)
        
        # 添加计算按钮和状态指示灯
        calc_layout = QHBoxLayout()
        calc_button = QPushButton("计算")
        calc_button.clicked.connect(self.update_branch_characteristics)
        calc_layout.addWidget(calc_button)
        
        calc_layout.addWidget(QLabel("运行状态"))
        self.calc_status = StatusLight()
        calc_layout.addWidget(self.calc_status)
        calc_layout.addStretch()
        
        eff_layout.addLayout(calc_layout)
        eff_group.setLayout(eff_layout)
        layout.addWidget(eff_group)
        
        panel.setLayout(layout)
        return panel

    def create_right_panel(self):
        panel = QGroupBox("结果分析")
        layout = QVBoxLayout()
        layout.setSpacing(5)  # 减小组件之间的间距
        layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        
        # N/P比例设置
        ratio_layout = QHBoxLayout()
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        ratio_layout.addWidget(QLabel("N型分支面积/P型分支面积"))
        self.ratio_edit = QLineEdit("0.1")
        ratio_layout.addWidget(self.ratio_edit)
        layout.addLayout(ratio_layout)
        
        # 1. 器件功率图表
        power_container, [power_ax], power_canvas = self.create_plot_widget(num_subplots=1, height=2.5)
        power_ax.set_title("器件功率")
        power_ax.set_xlabel("电流密度（A/cm2）")
        power_ax.set_ylabel("功率（W/cm2）")
        power_ax.set_xlim(0, 1)
        power_ax.set_ylim(0, 1)
        layout.addWidget(power_container)
        
        # 2. 器件效率图表
        efficiency_container, [efficiency_ax], efficiency_canvas = self.create_plot_widget(num_subplots=1, height=2.5)
        efficiency_ax.set_title("器件效率")
        efficiency_ax.set_xlabel("电流密度（A/cm2）")
        efficiency_ax.set_ylabel("效率")
        efficiency_ax.set_xlim(0, 1)
        efficiency_ax.set_ylim(0, 1)
        layout.addWidget(efficiency_container)
        
        # 最大功率点和最大效率点显示框
        results_layout = QHBoxLayout()
        results_layout.setSpacing(10)  # 减小显示框之间的间距
        results_layout.setContentsMargins(0, 0, 0, 0)
        
        # 最大功率点
        power_group = QGroupBox("最大功率点")
        power_layout = QVBoxLayout()
        power_layout.setSpacing(5)  # 减小内部组件的间距
        power_layout.setContentsMargins(5, 5, 5, 5)
        
        power_value_layout = QHBoxLayout()
        power_value_layout.addWidget(QLabel("最大功率"))
        self.max_power = QLineEdit()
        power_value_layout.addWidget(self.max_power)
        power_layout.addLayout(power_value_layout)
        
        power_current_layout = QHBoxLayout()
        power_current_layout.addWidget(QLabel("电流密度"))
        self.power_current = QLineEdit()
        power_current_layout.addWidget(self.power_current)
        power_layout.addLayout(power_current_layout)
        
        power_group.setLayout(power_layout)
        results_layout.addWidget(power_group)
        
        # 最大效率点
        eff_group = QGroupBox("最大效率点")
        eff_layout = QVBoxLayout()
        eff_layout.setSpacing(5)  # 减小内部组件的间距
        eff_layout.setContentsMargins(5, 5, 5, 5)
        
        eff_value_layout = QHBoxLayout()
        eff_value_layout.addWidget(QLabel("最大效率"))
        self.max_eff = QLineEdit()
        eff_value_layout.addWidget(self.max_eff)
        eff_layout.addLayout(eff_value_layout)
        
        eff_current_layout = QHBoxLayout()
        eff_current_layout.addWidget(QLabel("电流密度"))
        self.eff_current = QLineEdit()
        eff_current_layout.addWidget(self.eff_current)
        eff_layout.addLayout(eff_current_layout)
        
        eff_group.setLayout(eff_layout)
        results_layout.addWidget(eff_group)
        
        layout.addLayout(results_layout)
        
        # 3. 功率效率优化区间图表
        optimization_container, [optimization_ax], optimization_canvas = self.create_plot_widget(num_subplots=1, height=2.5)
        optimization_ax.set_title("功率效率优化区间")
        optimization_ax.set_xlabel("功率")
        optimization_ax.set_ylabel("效率")
        optimization_ax.set_xlim(0, 1)
        optimization_ax.set_ylim(0, 1)
        layout.addWidget(optimization_container)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)  # 减小按钮之间的间距
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.right_calc_button = QPushButton("计算")
        self.right_export_button = QPushButton("导出数据")
        button_layout.addWidget(self.right_calc_button)
        button_layout.addWidget(self.right_export_button)
        button_layout.addStretch()  # 添加弹性空间
        layout.addLayout(button_layout)
        
        panel.setLayout(layout)
        return panel

    def update_zt_plots(self):
        """更新优值系数图表，展示ZT随温度的变化"""
        try:
            # 获取当前选择的材料组分
            p_composition = self.p_type_combo.currentText()
            n_composition = self.n_type_combo.currentText()
            
            # 创建温度范围（300K - 700K），与MATLAB代码一致
            temperatures = np.arange(300, 701, 20)  # 300:20:700
            
            # 计算P型材料的优值系数
            p_zt = []
            for T in temperatures:
                # 直接从Excel文件中读取ZT值，与MATLAB代码一致
                interp_key = f"p_{p_composition}"
                if interp_key not in self.calculator.interpolators:
                    self.calculator.create_interpolators('p', p_composition)
                p_zt.append(self.calculator.calculate_zt('p', p_composition, T))
            
            # 计算N型材料的优值系数
            n_zt = []
            for T in temperatures:
                interp_key = f"n_{n_composition}"
                if interp_key not in self.calculator.interpolators:
                    self.calculator.create_interpolators('n', n_composition)
                n_zt.append(self.calculator.calculate_zt('n', n_composition, T))
            
            # 更新P型图表
            self.zt_axes[0].clear()
            self.zt_axes[0].plot(temperatures, p_zt, 'b+-', linewidth=2)  # 使用蓝色+号标记，与MATLAB一致
            self.zt_axes[0].set_title("P型半导体材料优值系数", pad=5)
            self.zt_axes[0].set_xlabel("温度 (K)")
            self.zt_axes[0].set_ylabel("ZT")
            self.zt_axes[0].set_xlim(300, 700)
            self.zt_axes[0].set_ylim(0, 2.0)  # 与MATLAB图形一致
            self.zt_axes[0].grid(True, linestyle='--', alpha=0.7)
            
            # 更新N型图表
            self.zt_axes[1].clear()
            self.zt_axes[1].plot(temperatures, n_zt, 'r*-', linewidth=2)  # 使用红色*号标记，与MATLAB一致
            self.zt_axes[1].set_title("N型半导体材料优值系数", pad=5)
            self.zt_axes[1].set_xlabel("温度 (K)")
            self.zt_axes[1].set_ylabel("ZT")
            self.zt_axes[1].set_xlim(300, 700)
            self.zt_axes[1].set_ylim(0, 2.0)  # 与MATLAB图形一致
            self.zt_axes[1].grid(True, linestyle='--', alpha=0.7)
            
            # 设置两个图表的共同属性
            for ax in self.zt_axes:
                ax.set_facecolor('#F8F8F8')
                ax.tick_params(direction='in')  # 刻度线向内
                ax.spines['top'].set_visible(True)
                ax.spines['right'].set_visible(True)
                # 设置主要刻度
                ax.set_xticks(np.arange(300, 701, 100))
                ax.set_yticks(np.arange(0, 2.1, 0.5))
                # 添加次要刻度
                ax.minorticks_on()
            
            # 刷新图表
            self.zt_canvas.draw()
            
        except Exception as e:
            print(f"更新优值系数图表错误: {str(e)}")
            import traceback
            traceback.print_exc()

    def initialize_calculation(self):
        """初始化运算"""
        try:
            print("\n===== 开始初始化计算 =====")
            # 更新状态指示灯为红色（计算中）
            self.status_light.set_status(False)
            QApplication.processEvents()  # 确保UI更新
            
            # 更新优值系数图表
            self.update_zt_plots()
            
            # 获取输入参数
            Th = float(self.th_edit.text())
            Tc = float(self.tc_edit.text())
            n_points = int(self.grid_edit.text())
            max_iter = int(self.iter_edit.text())  # 获取迭代次数
            
            print(f"输入参数: Th={Th}K, Tc={Tc}K, 格点数={n_points}")
            
            # 计算P型和N型材料的温度分布
            p_composition = self.p_type_combo.currentText()
            n_composition = self.n_type_combo.currentText()
            
            # 获取当前选择的电流密度
            p_current = float(self.p_current_combo.currentText())
            n_current = float(self.n_current_combo.currentText())
            
            print(f"P型材料: 组分={p_composition}, 电流密度={p_current}A/cm²")
            print(f"N型材料: 组分={n_composition}, 电流密度={n_current}A/cm²")
            
            # 将最大迭代次数传递给温度分布计算函数
            x_p, T_p = self.calculator.calculate_temperature_distribution(
                Th, Tc, n_points, 'p', p_composition, p_current, max_iter)
            x_n, T_n = self.calculator.calculate_temperature_distribution(
                Th, Tc, n_points, 'n', n_composition, n_current, max_iter)
            
            # 保存计算结果以便后续使用
            self.x_p, self.T_p = x_p, T_p
            self.x_n, self.T_n = x_n, T_n
            
            print("计算完成，正在更新温度分布图...")
            
            # 删除旧的点击事件处理器（如果存在）
            if hasattr(self, '_pick_cid') and self._pick_cid:
                self.temp_canvas.mpl_disconnect(self._pick_cid)
            
            # 更新温度分布图
            self.update_temperature_plots(x_p, T_p, x_n, T_n)
            
            # 计算完成，更新状态指示灯为绿色
            self.status_light.set_status(True)
            print("===== 初始化计算完成 =====")
            
        except Exception as e:
            print(f"初始化计算错误: {str(e)}")
            import traceback
            traceback.print_exc()
            self.status_light.set_status(False)
    
    def update_temperature_plots(self, x_p, T_p, x_n, T_n):
        """
        更新温度分布图，使横坐标随格点数变化，并支持数据点交互
        """
        try:
            # 使用保存的引用直接访问图表
            ax1, ax2 = self.temp_axes
            
            # 清除旧数据
            ax1.clear()
            ax2.clear()
            
            # 获取格点数量
            n_points_p = len(x_p)
            n_points_n = len(x_n)
            
            # 使用整数格点位置 1, 2, 3, ..., n
            grid_points_p = np.arange(1, n_points_p + 1)
            grid_points_n = np.arange(1, n_points_n + 1)
            
            print(f"\n=== 温度分布图数据 ===")
            print(f"P型格点数量: {n_points_p}")
            print(f"P型温度数据: {T_p}")
            print(f"N型格点数量: {n_points_n}")
            print(f"N型温度数据: {T_n}")
            
            # 绘制新数据 - 使用标记和细线
            p_line, = ax1.plot(grid_points_p, T_p, 'b*-', markersize=6, picker=5)  # 设置picker参数启用点击事件
            n_line, = ax2.plot(grid_points_n, T_n, 'r*-', markersize=6, picker=5)
            
            # 添加点击事件处理函数
            def on_pick(event):
                if event.artist == p_line:
                    ind = event.ind[0]
                    ax = ax1
                    grid_points = grid_points_p
                    temps = T_p
                    title = "P型材料"
                elif event.artist == n_line:
                    ind = event.ind[0]
                    ax = ax2
                    grid_points = grid_points_n
                    temps = T_n
                    title = "N型材料"
                else:
                    return
                
                # 显示详细信息
                pos = grid_points[ind]
                temp = temps[ind]
                
                # 移除之前的标注（如果有）
                for artist in ax.texts:
                    artist.remove()
                
                # 添加新标注
                ax.annotate(f'格点: {pos}\n温度: {temp:.2f}K',
                            xy=(pos, temp), xytext=(pos+0.5, temp+10),
                            arrowprops=dict(arrowstyle='->',
                                            connectionstyle='arc3,rad=.2',
                                            color='green'),
                            bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                            fontsize=8)
                
                # 更新图表
                self.temp_canvas.draw()
                
                # 输出详细数据到控制台
                print(f"{title} 格点位置 {pos} 的详细数据:")
                print(f"  温度: {temp:.2f}K")
            
            # 连接点击事件
            self._pick_cid = self.temp_canvas.mpl_connect('pick_event', on_pick)
            
            # 设置标题和标签
            ax1.set_title("格点温度分布（P型）")
            ax2.set_title("格点温度分布（N型）")
            
            # 获取温度的最小值和最大值，用于设置Y轴范围
            min_temp = min(min(T_p), min(T_n))
            max_temp = max(max(T_p), max(T_n))
            
            # 设置坐标轴范围和刻度
            for ax, n_points in zip([ax1, ax2], [n_points_p, n_points_n]):
                ax.set_xlabel("格点位置")
                ax.set_ylabel("温度 (K)")
                
                # 动态设置横坐标范围和刻度
                ax.set_xlim(0.5, n_points + 0.5)  # 添加边距
                
                # 如果格点数较多，则间隔显示刻度
                if n_points <= 20:
                    ax.set_xticks(range(1, n_points + 1))
                else:
                    step = max(1, n_points // 10)  # 最多显示10个刻度
                    ax.set_xticks(range(1, n_points + 1, step))
                
                # 设置Y轴范围
                y_margin = (max_temp - min_temp) * 0.1  # 添加10%的边距
                ax.set_ylim(min_temp - y_margin, max_temp + y_margin)
                
                # 添加网格
                ax.grid(True, linestyle='--', alpha=0.7)
            
            # 刷新图表
            self.temp_canvas.draw()
            print("温度分布图更新完成")
            
        except Exception as e:
            print(f"更新温度分布图错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def update_efficiency_plots(self):
        """更新效率图表，基于参考算法的计算方法"""
        try:
            # 使用保存的引用直接访问图表
            ax1, ax2 = self.eff_axes
            ax1.clear()
            ax2.clear()
            
            # 获取输入参数
            Th = float(self.th_edit.text())
            Tc = float(self.tc_edit.text())
            p_composition = self.p_type_combo.currentText()
            n_composition = self.n_type_combo.currentText()
            
            # 获取当前选择的电流密度
            current_p = float(self.p_current_combo.currentText())
            current_n = float(self.n_current_combo.currentText())
            
            # 获取温度分布
            x_p, T_p = self.x_p, self.T_p
            x_n, T_n = self.x_n, self.T_n
            
            # 设置与参考算法一致的电流密度范围
            p_currents = np.linspace(-30, 0, 16)  # P型电流密度范围
            n_currents = np.linspace(0, 50, 51)   # N型电流密度范围（0-50，步长1）
            
            # 计算P型效率
            p_efficiencies = []
            valid_p_currents = []
            for j in p_currents:
                eff, _ = self.calculator.calculate_efficiency(
                    Th, Tc, 'p', p_composition, j, x_p, T_p)
                if eff > 0:  # 只保留正效率值
                    p_efficiencies.append(eff)
                    valid_p_currents.append(j)
            
            # 计算N型效率
            n_efficiencies = []
            valid_n_currents = []
            for j in n_currents:
                eff, _ = self.calculator.calculate_efficiency(
                    Th, Tc, 'n', n_composition, j, x_n, T_n)
                if eff > 0:  # 只保留正效率值
                    n_efficiencies.append(eff)
                    valid_n_currents.append(j)
            
            # 计算当前电流密度的效率
            p_current_eff, _ = self.calculator.calculate_efficiency(
                Th, Tc, 'p', p_composition, current_p, x_p, T_p)
            n_current_eff, _ = self.calculator.calculate_efficiency(
                Th, Tc, 'n', n_composition, current_n, x_n, T_n)
            
            # 查找最大效率点
            if p_efficiencies:
                max_p_eff_idx = np.argmax(p_efficiencies)
                max_p_eff = p_efficiencies[max_p_eff_idx]
                max_p_j = valid_p_currents[max_p_eff_idx]
                print(f"P型最大效率: {max_p_eff:.4f}% 在电流密度 {max_p_j:.2f}A/cm²")
            
            if n_efficiencies:
                max_n_eff_idx = np.argmax(n_efficiencies)
                max_n_eff = n_efficiencies[max_n_eff_idx]
                max_n_j = valid_n_currents[max_n_eff_idx]
                print(f"N型最大效率: {max_n_eff:.4f}% 在电流密度 {max_n_j:.2f}A/cm²")
            
            # 绘制P型效率曲线
            if valid_p_currents:
                ax1.plot(valid_p_currents, p_efficiencies, 'b-', linewidth=1.5)
                ax1.scatter(valid_p_currents, p_efficiencies, color='blue', s=20, marker='o')
                
                # 标记当前选择的电流密度
                if p_current_eff > 0:
                    ax1.scatter(current_p, p_current_eff, color='red', s=80, marker='*', 
                               label=f'当前: {current_p}A/cm², {p_current_eff:.4f}%')
                
                # 标记最大效率点
                if p_efficiencies:
                    ax1.scatter(max_p_j, max_p_eff, color='green', s=80, marker='s',
                               label=f'最大: {max_p_j:.2f}A/cm², {max_p_eff:.4f}%')
                
                ax1.set_title("P型材料效率")
                ax1.set_xlabel("电流密度 (A/cm²)")
                ax1.set_ylabel("效率 (%)")
                
                # 设置P型电流密度范围，重点关注-2.5到0部分
                ax1.set_xlim(-5, 0)
                
                # 设置效率范围
                if p_efficiencies:
                    y_max = max(p_efficiencies) * 1.2
                    ax1.set_ylim(0, max(y_max, 5.0))
                else:
                    ax1.set_ylim(0, 5.0)
                    
                ax1.grid(True, linestyle='--', alpha=0.7)
                ax1.legend(loc='best', fontsize=8)
            else:
                ax1.text(0.5, 0.5, "未找到有效效率数据", 
                        ha='center', va='center', transform=ax1.transAxes)
                ax1.set_title("P型材料效率")
                ax1.set_xlabel("电流密度 (A/cm²)")
                ax1.set_ylabel("效率 (%)")
                ax1.set_xlim(-5, 0)
                ax1.set_ylim(0, 5.0)
            
            # 绘制N型效率曲线
            if valid_n_currents:
                ax2.plot(valid_n_currents, n_efficiencies, 'r-', linewidth=1.5)
                ax2.scatter(valid_n_currents, n_efficiencies, color='red', s=20, marker='o')
                
                # 标记当前选择的电流密度
                if n_current_eff > 0:
                    ax2.scatter(current_n, n_current_eff, color='blue', s=80, marker='*',
                               label=f'当前: {current_n}A/cm², {n_current_eff:.4f}%')
                
                # 标记最大效率点
                if n_efficiencies:
                    ax2.scatter(max_n_j, max_n_eff, color='green', s=80, marker='s',
                               label=f'最大: {max_n_j:.2f}A/cm², {max_n_eff:.4f}%')
                
                ax2.set_title("N型材料效率")
                ax2.set_xlabel("电流密度 (A/cm²)")
                ax2.set_ylabel("效率 (%)")
                
                # 设置N型横坐标范围为0-50
                ax2.set_xlim(0, 50)
                
                # 根据计算结果设置纵坐标范围
                if n_efficiencies:
                    y_max = max(n_efficiencies) * 1.2
                    ax2.set_ylim(0, max(y_max, 5.0))
                else:
                    ax2.set_ylim(0, 5.0)
                    
                ax2.grid(True, linestyle='--', alpha=0.7)
                ax2.legend(loc='best', fontsize=8)
            else:
                ax2.text(0.5, 0.5, "未找到有效效率数据", 
                        ha='center', va='center', transform=ax2.transAxes)
                ax2.set_title("N型材料效率")
                ax2.set_xlabel("电流密度 (A/cm²)")
                ax2.set_ylabel("效率 (%)")
                ax2.set_xlim(0, 50)
                ax2.set_ylim(0, 5.0)
            
            # 刷新图表
            self.eff_canvas.draw()
            print("效率图更新完成")
            
        except Exception as e:
            print(f"更新效率图错误: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def update_branch_characteristics(self):
        """更新分支特性"""
        try:
            print("开始更新分支特性...")
            # 更新状态指示灯为红色（计算中）
            self.calc_status.set_status(False)
            QApplication.processEvents()  # 确保UI更新
            
            # 执行计算
            self.initialize_calculation()
            
            # 更新效率图
            self.update_efficiency_plots()
            
            # 计算完成，更新状态指示灯为绿色
            self.calc_status.set_status(True)
            print("分支特性更新完成")
            
        except Exception as e:
            print(f"更新分支特性错误: {str(e)}")
            import traceback
            traceback.print_exc()
            self.calc_status.set_status(False)
    
    def calculate_device_performance(self):
        """计算器件性能"""
        try:
            # 获取中间面板的状态指示灯
            eff_group = self.findChild(QGroupBox, "材料效率")
            calc_status = eff_group.findChild(StatusLight)
            
            # 更新状态指示灯为红色（计算中）
            calc_status.set_status(False)
            QApplication.processEvents()  # 确保UI更新
            
            # 获取输入参数
            Th = float(self.th_edit.text())
            Tc = float(self.tc_edit.text())
            p_composition = self.p_type_combo.currentText()
            n_composition = self.n_type_combo.currentText()
            area_ratio = float(self.ratio_edit.text())
            
            print(f"\n===== 开始计算器件性能 =====")
            print(f"温度: Th={Th}K, Tc={Tc}K")
            print(f"材料: P型={p_composition}, N型={n_composition}")
            print(f"面积比(N/P): {area_ratio}")
            
            # 创建更合理的电流密度范围
            currents = np.linspace(0.1, 4, 40)  # 避免从0开始（可能导致除零错误）
            powers = []
            efficiencies = []
            
            # 获取当前温度分布
            x_p, T_p = self.x_p, self.T_p
            x_n, T_n = self.x_n, self.T_n
            
            # 计算每个电流密度下的功率和效率
            for j in currents:
                # P型和N型的电流密度
                j_p = -j  # P型为负
                j_n = j / area_ratio  # 考虑面积比
                
                # 计算P型和N型的效率和功率
                p_eff, p_power = self.calculator.calculate_efficiency(
                    Th, Tc, 'p', p_composition, j_p, x_p, T_p)
                n_eff, n_power = self.calculator.calculate_efficiency(
                    Th, Tc, 'n', n_composition, j_n, x_n, T_n)
                
                # 转换为百分比和适当单位
                p_eff = p_eff / 100  # 转回小数
                n_eff = n_eff / 100  # 转回小数
                
                # 根据面积比计算综合效率和功率
                # 假设P型和N型具有相同的热流输入密度
                p_area = 1 / (1 + area_ratio)  # P型面积占比
                n_area = area_ratio / (1 + area_ratio)  # N型面积占比
                
                # 计算总功率（考虑面积比）
                total_power = p_power * p_area + n_power * n_area
                
                # 计算总效率（加权平均）
                if p_eff > 0 and n_eff > 0:
                    total_efficiency = (p_eff * p_area + n_eff * n_area) / (p_area + n_area)
                else:
                    total_efficiency = 0
                
                powers.append(total_power / 10000)  # 转换为W/cm²
                efficiencies.append(total_efficiency)
            
            # 查找最大功率点和最大效率点
            if powers and max(powers) > 0:
                max_power_idx = np.argmax(powers)
                self.max_power.setText(f"{powers[max_power_idx]:.2e}")
                self.power_current.setText(f"{currents[max_power_idx]:.2f}")
                print(f"最大功率: {powers[max_power_idx]:.4e} W/cm² 在电流密度 {currents[max_power_idx]:.2f}A/cm²")
            else:
                self.max_power.setText("0")
                self.power_current.setText("0")
                print("未找到有效的最大功率点")
            
            if efficiencies and max(efficiencies) > 0:
                max_eff_idx = np.argmax(efficiencies)
                self.max_eff.setText(f"{efficiencies[max_eff_idx]:.2%}")
                self.eff_current.setText(f"{currents[max_eff_idx]:.2f}")
                print(f"最大效率: {efficiencies[max_eff_idx]:.4%} 在电流密度 {currents[max_eff_idx]:.2f}A/cm²")
            else:
                self.max_eff.setText("0")
                self.eff_current.setText("0")
                print("未找到有效的最大效率点")
            
            # 更新功率图
            power_container = self.findChild(QGroupBox, "器件功率").findChildren(FigureCanvas)[0]
            power_fig = power_container.figure
            power_ax = power_fig.axes[0]
            power_ax.clear()
            power_ax.plot(currents, powers, 'b-', linewidth=1.5, label='功率曲线')
            
            if max(powers) > 0:
                power_ax.scatter(currents[max_power_idx], powers[max_power_idx], 
                               color='red', marker='o', s=50, label='最大功率点')
            
            power_ax.set_xlabel("电流密度 (A/cm²)")
            power_ax.set_ylabel("功率 (W/cm²)")
            power_ax.set_xlim(0, max(currents))
            power_ax.set_ylim(0, max(max(powers)*1.1, 1e-6))
            power_ax.grid(True, linestyle='--', alpha=0.6)
            power_ax.legend(loc='best')
            power_ax.set_facecolor('#F8F8F8')
            power_fig.canvas.draw()
            
            # 更新效率图
            eff_container = self.findChild(QGroupBox, "器件效率").findChildren(FigureCanvas)[0]
            eff_fig = eff_container.figure
            eff_ax = eff_fig.axes[0]
            eff_ax.clear()
            eff_ax.plot(currents, [e*100 for e in efficiencies], 'r-', linewidth=1.5, label='效率曲线')
            
            if max(efficiencies) > 0:
                eff_ax.scatter(currents[max_eff_idx], efficiencies[max_eff_idx]*100, 
                             color='blue', marker='o', s=50, label='最大效率点')
            
            eff_ax.set_xlabel("电流密度 (A/cm²)")
            eff_ax.set_ylabel("效率 (%)")
            eff_ax.set_xlim(0, max(currents))
            eff_ax.set_ylim(0, max(max([e*100 for e in efficiencies])*1.1, 0.1))
            eff_ax.grid(True, linestyle='--', alpha=0.6)
            eff_ax.legend(loc='best')
            eff_ax.set_facecolor('#F8F8F8')
            eff_fig.canvas.draw()
            
            # 更新优化区间图
            if powers and efficiencies and max(powers) > 0 and max(efficiencies) > 0:
                opt_container = self.findChild(QGroupBox, "功率效率优化区间").findChildren(FigureCanvas)[0]
                opt_fig = opt_container.figure
                opt_ax = opt_fig.axes[0]
                opt_ax.clear()
                opt_ax.plot(powers, [e*100 for e in efficiencies], 'g-', label='优化曲线')
                opt_ax.scatter(powers[max_power_idx], efficiencies[max_power_idx]*100, 
                             color='red', marker='o', label='最大功率点')
                opt_ax.scatter(powers[max_eff_idx], efficiencies[max_eff_idx]*100, 
                             color='blue', marker='o', label='最大效率点')
                opt_ax.set_xlabel("功率 (W/cm²)")
                opt_ax.set_ylabel("效率 (%)")
                opt_ax.grid(True, linestyle='--', alpha=0.6)
                opt_ax.legend(loc='best')
                opt_fig.canvas.draw()
            
            # 计算完成，更新状态指示灯为绿色
            calc_status.set_status(True)
            print("===== 器件性能计算完成 =====")
            
        except Exception as e:
            print(f"计算器件性能错误: {str(e)}")
            import traceback
            traceback.print_exc()
            calc_status.set_status(False)

    def export_data(self):
        """导出数据到文件"""
        try:
            from datetime import datetime
            import pandas as pd
            
            # 获取当前时间作为文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"thermoelectric_data_{timestamp}.xlsx"
            
            # 创建Excel写入器
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # 获取所有计算数据
                data = {
                    "高温温度(K)": [float(self.th_edit.text())],
                    "低温温度(K)": [float(self.tc_edit.text())],
                    "P型材料": [self.p_type_combo.currentText()],
                    "N型材料": [self.n_type_combo.currentText()],
                    "N/P面积比": [float(self.ratio_edit.text())],
                    "最大功率(W/cm2)": [float(self.max_power.text())],
                    "最大功率电流密度(A/cm2)": [float(self.power_current.text())],
                    "最大效率": [float(self.max_eff.text())],
                    "最大效率电流密度(A/cm2)": [float(self.eff_current.text())]
                }
                
                # 创建数据帧并保存
                df = pd.DataFrame(data)
                df.to_excel(writer, sheet_name='计算结果', index=False)
            
            # 确保工作表可见
            workbook = writer.book
            if workbook.sheetnames:
                workbook.active = workbook.sheetnames.index('计算结果')
        
            print(f"数据已导出到文件: {filename}")
            
        except Exception as e:
            print(f"导出数据错误: {str(e)}")

    def analyze_material_performance(self, material_type, composition, current_density):
        """分析材料性能并可视化结果，帮助查找问题"""
        try:
            if not hasattr(self, 'last_calc_data'):
                print("尚未执行效率计算，请先计算效率")
                return
                
            data = self.last_calc_data
            
            # 创建一个2x2的可视化图表
            fig, axes = plt.subplots(2, 2, figsize=(12, 10))
            fig.suptitle(f"{material_type}型材料 (组分={composition}, 电流密度={current_density}A/cm²) 性能分析", fontsize=14)
            
            # 1. 温度分布
            ax1 = axes[0, 0]
            x_range = np.arange(1, len(data['temperature']) + 1)
            ax1.plot(x_range, data['temperature'], 'b-o')
            ax1.set_title('温度分布')
            ax1.set_xlabel('格点位置')
            ax1.set_ylabel('温度 (K)')
            ax1.grid(True)
            
            # 2. 材料属性随温度变化
            ax2 = axes[0, 1]
            ax2.plot(data['temperature'], data['seebeck'] * 1e6, 'r-', label='塞贝克系数 (μV/K)')
            ax2.set_xlabel('温度 (K)')
            ax2.set_ylabel('塞贝克系数 (μV/K)')
            ax2.set_title('塞贝克系数分布')
            ax2.grid(True)
            
            ax2_twin = ax2.twinx()
            ax2_twin.plot(data['temperature'], data['resistivity'] * 1e6, 'g-', label='电阻率 (μΩ·m)')
            ax2_twin.set_ylabel('电阻率 (μΩ·m)')
            
            # 添加双轴图例
            lines1, labels1 = ax2.get_legend_handles_labels()
            lines2, labels2 = ax2_twin.get_legend_handles_labels()
            ax2.legend(lines1 + lines2, labels1 + labels2, loc='best')
            
            # 3. 能量流动分析
            ax3 = axes[1, 0]
            seebeck_power = data['seebeck'] * data['dTdx'] * data['current_density']
            joule_heat = data['resistivity'] * data['current_density']**2
            
            ax3.plot(x_range, seebeck_power, 'b-', label='塞贝克功率')
            ax3.plot(x_range, joule_heat, 'r-', label='焦耳热损失')
            ax3.plot(x_range, seebeck_power - joule_heat, 'g-', label='净功率')
            ax3.set_title('能量流动分析')
            ax3.set_xlabel('格点位置')
            ax3.set_ylabel('功率密度 (W/m³)')
            ax3.grid(True)
            ax3.legend()
            
            # 4. 热流分析
            ax4 = axes[1, 1]
            fourier_heat = data['thermal_cond'] * data['dTdx']
            peltier_heat = data['current_density'] * data['seebeck'] * data['temperature']
            ax4.plot(x_range, fourier_heat, 'b-', label='傅里叶热流')
            ax4.plot(x_range, peltier_heat, 'r-', label='帕尔贴热流')
            ax4.plot(x_range, fourier_heat - peltier_heat, 'g-', label='净热流')
            ax4.set_title('热流分析')
            ax4.set_xlabel('格点位置')
            ax4.set_ylabel('热流密度 (W/m²)')
            ax4.grid(True)
            ax4.legend()
            
            plt.tight_layout()
            plt.show()
            
            # 打印能量平衡分析
            print("\n===== 能量平衡分析 =====")
            heat_in = abs(fourier_heat[0] - peltier_heat[0])
            heat_out = abs(fourier_heat[-1] - peltier_heat[-1])
            total_joule = np.sum(joule_heat) * (x_range[-1] - x_range[0]) / (len(x_range) - 1)
            total_power = np.sum(seebeck_power - joule_heat) * (x_range[-1] - x_range[0]) / (len(x_range) - 1)
            
            print(f"入口热流: {heat_in:.3e} W/m²")
            print(f"出口热流: {heat_out:.3e} W/m²")
            print(f"总焦耳热: {total_joule:.3e} W/m²")
            print(f"总功率输出: {total_power:.3e} W/m²")
            print(f"热平衡差值: {(heat_in - heat_out - total_power):.3e} W/m² (理论上应接近0)")
            
        except Exception as e:
            print(f"性能分析错误: {str(e)}")
            import traceback
            traceback.print_exc()

    def analyze_efficiency_curve(self, material_type, composition):
        """分析材料效率曲线，帮助调试和对比论文结果"""
        try:
            # 获取温度设置
            Th = float(self.th_edit.text())
            Tc = float(self.tc_edit.text())
            
            # 获取温度分布
            x = self.x_p if material_type == 'p' else self.x_n
            T = self.T_p if material_type == 'p' else self.T_n
            
            # 设置电流密度范围，与论文对应
            if material_type == 'p':
                currents = np.linspace(-2.5, 0.0, 26)  # P型范围
                title = f"P型材料 ({composition}) 效率曲线分析"
            else:
                currents = np.linspace(20.0, 50.0, 31)  # N型范围
                title = f"N型材料 ({composition}) 效率曲线分析"
            
            # 计算效率
            efficiencies = []
            powers = []
            valid_currents = []
            
            for j in currents:
                eff, power = self.calculator.calculate_efficiency(
                    Th, Tc, material_type, composition, j, x, T)
                if eff > 0:  # 只保留正效率值
                    efficiencies.append(eff)
                    powers.append(power)
                    valid_currents.append(j)
            
            # 创建图表
            plt.figure(figsize=(10, 6))
            plt.plot(valid_currents, efficiencies, 'bo-', linewidth=1.5, markersize=4)
            
            # 添加最大效率点
            if efficiencies:
                max_idx = np.argmax(efficiencies)
                plt.scatter(valid_currents[max_idx], efficiencies[max_idx], color='red', s=100, marker='*')
                plt.annotate(f'最大效率: {efficiencies[max_idx]:.4f}%\n电流密度: {valid_currents[max_idx]:.2f}A/cm²', 
                            xy=(valid_currents[max_idx], efficiencies[max_idx]),
                            xytext=(valid_currents[max_idx] + 0.1, efficiencies[max_idx] - 0.002),
                            arrowprops=dict(arrowstyle='->'))
            
            # 设置图表属性
            plt.title(title)
            plt.xlabel("电流密度 (A/cm²)")
            plt.ylabel("效率 (%)")
            plt.grid(True, linestyle='--', alpha=0.7)
            
            # 设置坐标轴范围，与论文图7.2对应
            if material_type == 'p':
                plt.xlim(-2.5, 0.0)
            else:
                plt.xlim(20.0, 50.0)
                
            if efficiencies:
                plt.ylim(0, max(efficiencies) * 1.1)
            else:
                plt.ylim(0, 0.05)  # 默认范围0-5%
            
            # 添加注释信息
            plt.figtext(0.02, 0.02, f"温度设置: Th={Th}K, Tc={Tc}K", fontsize=9)
            
            # 添加卡诺效率参考线
            carnot_eff = (Th - Tc) / Th * 100
            plt.axhline(y=carnot_eff, color='r', linestyle='--', alpha=0.5)
            plt.annotate(f'卡诺效率: {carnot_eff:.2f}%', 
                        xy=(valid_currents[0] if valid_currents else currents[0], carnot_eff),
                        xytext=(valid_currents[0] if valid_currents else currents[0], carnot_eff + 0.002),
                        fontsize=8)
            
            plt.tight_layout()
            plt.show()
            
            # 打印数据统计
            print(f"\n======= {title} =======")
            print(f"温度设置: Th={Th}K, Tc={Tc}K")
            print(f"卡诺效率: {carnot_eff:.4f}%")
            
            if efficiencies:
                max_idx = np.argmax(efficiencies)
                print(f"最大效率: {efficiencies[max_idx]:.4f}% 在电流密度 {valid_currents[max_idx]:.2f}A/cm²")
                print(f"效率值范围: {min(efficiencies):.4f}% - {max(efficiencies):.4f}%")
                print(f"相对卡诺效率: {(max(efficiencies)/carnot_eff*100):.2f}%")
            else:
                print("未找到有效效率数据")
            
        except Exception as e:
            print(f"效率曲线分析错误: {str(e)}")
            import traceback
            traceback.print_exc()

    def update_p_current_range(self):
        """更新P型材料电流密度范围，专注于-2.5到0区间"""
        self.p_current_combo.clear()
        self.p_current_combo.addItems(["-2.5", "-2.0", "-1.5", "-1.0", "-0.5"])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ThermoelectricApp()
    window.show()
    sys.exit(app.exec_())
