"""
會議紀錄模板生成器
生成標準化的會議紀錄模板，供LLM使用
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

class MeetingMinutesGenerator:
    """會議紀錄模板生成器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_template(self, 
                         meeting_title: str = "[Meeting Title]",
                         date: Optional[str] = None,
                         start_time: str = "HH:MM",
                         end_time: str = "HH:MM",
                         attendees: List[Dict[str, str]] = None,
                         agenda_items: List[str] = None,
                         status: str = "Draft agenda",
                         custom_notes: str = "") -> str:
        """
        生成會議紀錄模板
        
        Args:
            meeting_title: 會議標題
            date: 會議日期 (YYYY-MM-DD格式)，如果為None則使用今天
            start_time: 開始時間 (HH:MM格式)
            end_time: 結束時間 (HH:MM格式)
            attendees: 參與者列表，格式為 [{"name": "姓名", "role": "角色"}]
            agenda_items: 議程項目列表
            status: 會議狀態 ("Draft agenda" 或 "Complete")
            custom_notes: 自定義備註
            
        Returns:
            格式化的會議紀錄模板字符串
        """
        try:
            # 處理日期
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            # 處理參與者
            if attendees is None:
                attendees = [
                    {"name": "[Name 1]", "role": "[Role]"},
                    {"name": "[Name 2]", "role": "[Role]"},
                    {"name": "[Name 3]", "role": "[Role]"}
                ]
            
            # 處理議程項目
            if agenda_items is None:
                agenda_items = [
                    "[Agenda item 1]",
                    "[Agenda item 2]",
                    "[Agenda item 3]"
                ]
            
            # 生成參與者列表
            attendees_text = ""
            for attendee in attendees:
                attendees_text += f"- {attendee['name']} - {attendee['role']}\n"
            
            # 生成議程列表
            agenda_text = ""
            for i, item in enumerate(agenda_items, 1):
                agenda_text += f"{i}. {item}\n"
            
            # 計算下次會議日期（預設為一週後）
            next_meeting_date = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
            
            # 生成模板
            template = f"""# {meeting_title}

**Date:** {date}  
**Time:** {start_time} - {end_time}  
**Tags:** #meeting 
**Status:** {status}

---

## Attendees

{attendees_text.rstrip()}

## Agenda

{agenda_text.rstrip()}

---

## Discussion

### [Topic 1]

Key points discussed:
- Point 1
- Point 2

### [Topic 2]

Key points discussed:
- Point 1
- Point 2

---

## Decisions Made

- [ ] Decision 1
- [ ] Decision 2
- [ ] Decision 3

## Action Items

- [ ] **[Person]**: [Action item 1] - Due: YYYY-MM-DD
- [ ] **[Person]**: [Action item 2] - Due: next meeting
- [ ] **[Person]**: [Action item 3] - Due: next week

## Next Steps

- Next meeting scheduled for: {next_meeting_date}
- Topics for next meeting:
  - Topic 1
  - Topic 2

---

## Notes

{custom_notes if custom_notes else "Additional context, links, or references."}

"""
            
            self.logger.info(f"成功生成會議紀錄模板: {meeting_title}")
            return template
            
        except Exception as e:
            self.logger.error(f"生成會議紀錄模板時發生錯誤: {str(e)}")
            raise
    
    def generate_from_audio_metadata(self, 
                                   audio_metadata: Dict[str, Any],
                                   custom_attendees: List[Dict[str, str]] = None,
                                   custom_agenda: List[str] = None) -> str:
        """
        從音頻檔案元數據生成會議紀錄模板
        
        Args:
            audio_metadata: 音頻檔案的元數據
            custom_attendees: 自定義參與者列表
            custom_agenda: 自定義議程列表
            
        Returns:
            格式化的會議紀錄模板字符串
        """
        try:
            # 從音頻檔案名稱推斷會議標題
            file_name = audio_metadata.get('name', 'Unknown Meeting')
            meeting_title = self._extract_meeting_title(file_name)
            
            # 從檔案修改時間推斷會議日期
            modified_time = audio_metadata.get('modifiedTime')
            if modified_time:
                try:
                    # 解析ISO格式時間
                    dt = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
                    date = dt.strftime("%Y-%m-%d")
                except:
                    date = None
            else:
                date = None
            
            # 生成模板
            return self.generate_template(
                meeting_title=meeting_title,
                date=date,
                attendees=custom_attendees,
                agenda_items=custom_agenda
            )
            
        except Exception as e:
            self.logger.error(f"從音頻元數據生成會議紀錄模板時發生錯誤: {str(e)}")
            raise
    
    def _extract_meeting_title(self, file_name: str) -> str:
        """
        從檔案名稱提取會議標題
        
        Args:
            file_name: 檔案名稱
            
        Returns:
            提取的會議標題
        """
        try:
            # 移除副檔名
            name_without_ext = file_name.rsplit('.', 1)[0]
            
            # 移除常見的日期時間格式
            import re
            
            # 移除 YYYY-MM-DD 格式
            name_without_ext = re.sub(r'\d{4}-\d{2}-\d{2}', '', name_without_ext)
            
            # 移除 HH-MM 或 HH_MM 格式
            name_without_ext = re.sub(r'\d{2}[-_]\d{2}', '', name_without_ext)
            
            # 移除多餘的空格和特殊字符
            name_without_ext = re.sub(r'[_-]+', ' ', name_without_ext)
            name_without_ext = name_without_ext.strip()
            
            # 如果清理後為空，使用原始檔案名
            if not name_without_ext:
                name_without_ext = file_name.rsplit('.', 1)[0]
            
            return name_without_ext or "Meeting"
            
        except Exception as e:
            self.logger.warning(f"提取會議標題時發生錯誤: {str(e)}")
            return file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
    
    def get_template_variants(self) -> Dict[str, str]:
        """
        獲取不同類型的會議紀錄模板變體
        
        Returns:
            包含不同模板類型的字典
        """
        return {
            "standard": "標準會議紀錄模板",
            "standup": "每日站會模板",
            "retrospective": "回顧會議模板",
            "planning": "規劃會議模板",
            "review": "審查會議模板"
        }
    
    def generate_variant_template(self, variant: str, **kwargs) -> str:
        """
        生成特定類型的會議紀錄模板
        
        Args:
            variant: 模板類型
            **kwargs: 其他參數
            
        Returns:
            特定類型的會議紀錄模板
        """
        try:
            if variant == "standup":
                return self._generate_standup_template(**kwargs)
            elif variant == "retrospective":
                return self._generate_retrospective_template(**kwargs)
            elif variant == "planning":
                return self._generate_planning_template(**kwargs)
            elif variant == "review":
                return self._generate_review_template(**kwargs)
            else:
                return self.generate_template(**kwargs)
                
        except Exception as e:
            self.logger.error(f"生成{variant}模板時發生錯誤: {str(e)}")
            raise
    
    def _generate_standup_template(self, **kwargs) -> str:
        """生成每日站會模板"""
        template = self.generate_template(**kwargs)
        # 替換標準議程為站會專用議程
        standup_agenda = """1. 昨天完成了什麼？
2. 今天計劃做什麼？
3. 遇到什麼阻礙？"""
        
        template = template.replace(
            "1. [Agenda item 1]\n2. [Agenda item 2]\n3. [Agenda item 3]",
            standup_agenda
        )
        
        return template
    
    def _generate_retrospective_template(self, **kwargs) -> str:
        """生成回顧會議模板"""
        template = self.generate_template(**kwargs)
        # 替換標準議程為回顧會議專用議程
        retro_agenda = """1. 什麼做得好？
2. 什麼可以改進？
3. 下次要做什麼不同的事？"""
        
        template = template.replace(
            "1. [Agenda item 1]\n2. [Agenda item 2]\n3. [Agenda item 3]",
            retro_agenda
        )
        
        return template
    
    def _generate_planning_template(self, **kwargs) -> str:
        """生成規劃會議模板"""
        template = self.generate_template(**kwargs)
        # 替換標準議程為規劃會議專用議程
        planning_agenda = """1. 回顧上週目標完成情況
2. 本週目標設定
3. 資源分配與時程規劃
4. 風險評估與應對策略"""
        
        template = template.replace(
            "1. [Agenda item 1]\n2. [Agenda item 2]\n3. [Agenda item 3]",
            planning_agenda
        )
        
        return template
    
    def _generate_review_template(self, **kwargs) -> str:
        """生成審查會議模板"""
        template = self.generate_template(**kwargs)
        # 替換標準議程為審查會議專用議程
        review_agenda = """1. 審查項目進度
2. 品質檢查結果
3. 問題與風險討論
4. 下階段計劃確認"""
        
        template = template.replace(
            "1. [Agenda item 1]\n2. [Agenda item 2]\n3. [Agenda item 3]",
            review_agenda
        )
        
        return template