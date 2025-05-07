import re
import logging
from typing import List, Dict, Any


class NotionFormatter:
    """
    Notion 格式化工具類別
    負責將 Markdown 格式轉換為 Notion API 所需的區塊格式
    """
    
    def __init__(self):
        """初始化 Notion 格式化工具"""
        pass

    def process_note_format_for_notion(self, markdown_text: str) -> List[Dict[str, Any]]:
        """
        將 Markdown 格式的筆記轉換為 Notion API 所需的區塊格式
        
        Args:
            markdown_text: Markdown 格式的筆記內容
            
        Returns:
            Notion 區塊列表
        """
        if not markdown_text:
            return []
            
        blocks = []
        lines = markdown_text.split('\n')
        
        # 追蹤當前列表狀態
        current_list_type = None  # 'bulleted_list' 或 'numbered_list'
        list_items = []
        
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            
            # 空行處理 - 結束當前列表
            if not line.strip() and current_list_type:
                # 將累積的列表項目添加為列表區塊
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                i += 1
                continue
            
            # 標題處理
            header_match = re.match(r'^(#{1,3})\s+(.+)$', line)
            if header_match:
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                
                if level == 1:
                    blocks.append({
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [{"type": "text", "text": {"content": title}}],
                            "color": "default"
                        }
                    })
                elif level == 2:
                    blocks.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": title}}],
                            "color": "default"
                        }
                    })
                else:  # level == 3
                    blocks.append({
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {
                            "rich_text": [{"type": "text", "text": {"content": title}}],
                            "color": "default"
                        }
                    })
                i += 1
                continue
            
            # 水平線處理
            if line == '---' or line == '***' or line == '___':
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                    
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                })
                i += 1
                continue
            
            # 無序列表處理
            ul_match = re.match(r'^(\s*)[*\-+]\s+(.+)$', line)
            if ul_match:
                # 如果切換了列表類型，先添加之前的列表
                if current_list_type and current_list_type != "bulleted_list":
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                
                current_list_type = "bulleted_list"
                list_items.append(ul_match.group(2).strip())
                i += 1
                continue
            
            # 有序列表處理
            ol_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
            if ol_match:
                # 如果切換了列表類型，先添加之前的列表
                if current_list_type and current_list_type != "numbered_list":
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                
                current_list_type = "numbered_list"
                list_items.append(ol_match.group(2).strip())
                i += 1
                continue
            
            # 引用區塊處理
            if line.startswith('> '):
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                
                quote_text = line[2:].strip()
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": quote_text}}],
                        "color": "default"
                    }
                })
                i += 1
                continue
            
            # 代碼區塊處理
            if line.startswith('```'):
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                
                # 提取語言（如果有）
                lang = line[3:].strip()
                code_lines = []
                
                # 收集代碼區塊內容
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                    
                # 跳過結束的 ```
                if i < len(lines):
                    i += 1
                
                code_text = '\n'.join(code_lines)
                blocks.append({
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": code_text}}],
                        "language": lang if lang else "plain text"
                    }
                })
                continue
            
            # 圖片/連結處理（簡單替換為純文本，因為 Notion API 對內嵌媒體處理較複雜）
            # 這部分僅作為基本處理，實際應用可能需要更複雜的邏輯
            img_match = re.search(r'!\[(.+?)\]\((.+?)\)', line)
            if img_match and img_match.group(0) == line.strip():
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                
                alt_text = img_match.group(1)
                img_url = img_match.group(2)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": f"圖片: {alt_text} ({img_url})"}}],
                    }
                })
                i += 1
                continue
            
            # 普通段落處理
            # 如果不是空行且之前的內容均不匹配
            if line.strip() and not current_list_type:
                # 處理行內格式（粗體、斜體等）
                formatted_text = self._process_inline_format(line)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": formatted_text
                    }
                })
                i += 1
                continue
                
            # 其他情況 - 作為普通段落處理
            if line.strip():
                # 如果有未完成的列表，先添加
                if list_items:
                    blocks.extend(self._create_list_blocks(list_items, current_list_type))
                    list_items = []
                    current_list_type = None
                
                # 處理行內格式（粗體、斜體等）
                formatted_text = self._process_inline_format(line)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": formatted_text
                    }
                })
            
            i += 1
        
        # 處理最後剩餘的列表項目
        if list_items:
            blocks.extend(self._create_list_blocks(list_items, current_list_type))
        
        return blocks
    
    def _create_list_blocks(self, items: List[str], list_type: str) -> List[Dict[str, Any]]:
        """
        創建列表區塊
        
        Args:
            items: 列表項目
            list_type: 列表類型 (bulleted_list 或 numbered_list)
            
        Returns:
            列表區塊列表
        """
        blocks = []
        for item in items:
            formatted_text = self._process_inline_format(item)
            blocks.append({
                "object": "block",
                "type": list_type,
                list_type: {
                    "rich_text": formatted_text,
                    "color": "default"
                }
            })
        return blocks
    
    def _process_inline_format(self, text: str) -> List[Dict[str, Any]]:
        """
        處理行內格式 (粗體、斜體、連結等)
        
        Args:
            text: 需要處理的文本
            
        Returns:
            Notion rich_text 格式的列表
        """
        segments = []
        result = []
        
        # 處理連結 [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        
        # 處理粗體 **text** 或 __text__
        bold_pattern = r'(\*\*|__)(.*?)\1'
        
        # 處理斜體 *text* 或 _text_
        italic_pattern = r'(?<!\*|_)(\*|_)((?!\1).*?)(?<!\1)\1(?!\*|_)'
        
        # 處理刪除線 ~~text~~
        strike_pattern = r'~~(.*?)~~'
        
        # 處理代碼 `text`
        code_pattern = r'`(.*?)`'
        
        # 組合所有模式
        combined_pattern = f'({link_pattern})|({bold_pattern})|({italic_pattern})|({strike_pattern})|({code_pattern})'
        
        # 分割文本
        last_end = 0
        for match in re.finditer(combined_pattern, text):
            # 處理匹配前的普通文本
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    segments.append({
                        "type": "plain",
                        "text": plain_text
                    })
            
            # 處理匹配的特殊格式
            match_text = match.group(0)
            
            # 處理連結
            link_match = re.match(link_pattern, match_text)
            if link_match:
                segments.append({
                    "type": "link",
                    "text": link_match.group(1),
                    "url": link_match.group(2)
                })
            
            # 處理粗體
            elif re.match(bold_pattern, match_text):
                content = re.match(bold_pattern, match_text).group(2)
                segments.append({
                    "type": "bold",
                    "text": content
                })
            
            # 處理斜體
            elif re.match(italic_pattern, match_text):
                content = re.match(italic_pattern, match_text).group(2)
                segments.append({
                    "type": "italic",
                    "text": content
                })
            
            # 處理刪除線
            elif re.match(strike_pattern, match_text):
                content = re.match(strike_pattern, match_text).group(1)
                segments.append({
                    "type": "strike",
                    "text": content
                })
            
            # 處理代碼
            elif re.match(code_pattern, match_text):
                content = re.match(code_pattern, match_text).group(1)
                segments.append({
                    "type": "code",
                    "text": content
                })
            
            last_end = match.end()
        
        # 處理剩餘的普通文本
        if last_end < len(text):
            plain_text = text[last_end:]
            if plain_text:
                segments.append({
                    "type": "plain",
                    "text": plain_text
                })
        
        # 如果沒有找到特殊格式，直接返回原文本
        if not segments:
            return [{"type": "text", "text": {"content": text}}]
        
        # 轉換為 Notion rich_text 格式
        for segment in segments:
            if segment["type"] == "plain":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"]}
                })
            elif segment["type"] == "link":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"], "link": {"url": segment["url"]}}
                })
            elif segment["type"] == "bold":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"]},
                    "annotations": {"bold": True}
                })
            elif segment["type"] == "italic":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"]},
                    "annotations": {"italic": True}
                })
            elif segment["type"] == "strike":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"]},
                    "annotations": {"strikethrough": True}
                })
            elif segment["type"] == "code":
                result.append({
                    "type": "text",
                    "text": {"content": segment["text"]},
                    "annotations": {"code": True}
                })
        
        return result

    def split_transcript_into_blocks(self, transcript_text: str) -> List[Dict[str, Any]]:
        """
        將逐字稿拆分為 Notion 區塊
        
        Args:
            transcript_text: 逐字稿文本
            
        Returns:
            Notion 區塊列表
        """
        blocks = []
        
        # 按行拆分
        lines = transcript_text.split('\n')
        
        for line in lines:
            if not line.strip():
                continue
                
            # 檢查是否有講者標記 ([SPEAKER]: text 或 SPEAKER: text)
            speaker_match = re.match(r'(?:\[([^\]]+)\]:|([^:]+):)\s*(.*)', line)
            
            if speaker_match:
                speaker = speaker_match.group(1) or speaker_match.group(2)
                text = speaker_match.group(3).strip()
                
                # 創建段落區塊，加粗講者名稱
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": f"{speaker}: "},
                                "annotations": {"bold": True}
                            },
                            {
                                "type": "text",
                                "text": {"content": text}
                            }
                        ]
                    }
                })
            else:
                # 普通段落
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    }
                })
        
        return blocks
