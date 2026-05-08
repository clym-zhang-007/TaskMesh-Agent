"""
技能加载模块

实现双层技能加载机制，避免系统提示词膨胀。

双层加载策略：
- Layer 1（轻量）：技能名称和描述注入系统提示词（~100 tokens/skill）
- Layer 2（按需）：完整技能内容通过 tool_result 注入

目录结构：
    skills/
      pdf/
        SKILL.md          <-- frontmatter (name, description) + body
      code-review/
        SKILL.md

系统提示词示例：
    You are a coding agent.
    Skills available:
      - pdf: Process PDF files...        <-- Layer 1: 元数据
      - code-review: Review code...

当模型调用 load_skill("pdf") 时：
    tool_result:
    <skill>
      Full PDF processing instructions   <-- Layer 2: 完整内容
      Step 1: ...
      Step 2: ...
    </skill>

核心思想：不要把所有专业知识都塞进系统提示词，按需加载。

"""

import re
import yaml
from pathlib import Path
from typing import Dict, Tuple


class SkillLoader:
    """
    技能加载器
    
    扫描 skills/ 目录下的所有 SKILL.md 文件，解析 YAML frontmatter。
    提供双层加载机制：
    - Layer 1: get_descriptions() 返回简短描述
    - Layer 2: get_content(name) 返回完整内容
    
    Attributes:
        skills_dir (Path): 技能目录路径
        skills (Dict): 已加载的技能字典
    
    Example:
        >>> loader = SkillLoader(Path("skills"))
        >>> print(loader.get_descriptions())
        - pdf: Process PDF files
        - code-review: Review code quality
        >>> content = loader.get_content("pdf")
        >>> print(content)
        <skill name="pdf">
        ...完整的 PDF 处理指南...
        </skill>
    """
    
    def __init__(self, skills_dir: Path):
        """
        初始化技能加载器
        
        Args:
            skills_dir: 技能目录路径
        """
        self.skills_dir = skills_dir
        self.skills: Dict[str, Dict] = {}
        self._load_all()
    
    def _load_all(self):
        """
        启动时扫描 skills/ 目录下所有的 SKILL.md 文件并解析
        
        遍历所有子目录，查找 SKILL.md 文件，解析 frontmatter 和正文。
        """
        if not self.skills_dir.exists():
            print(f"[WARN] Skills directory not found: {self.skills_dir}")
            return
        
        skill_files = list(self.skills_dir.rglob("SKILL.md"))
        if not skill_files:
            print(f"[WARN] No SKILL.md files found in {self.skills_dir}")
            return
        
        for f in sorted(skill_files):
            try:
                text = f.read_text(encoding='utf-8')
                meta, body = self._parse_frontmatter(text)
                
                # 技能名称优先使用 YAML 中的 name 字段，否则用目录名
                name = meta.get("name", f.parent.name)
                
                self.skills[name] = {
                    "meta": meta,
                    "body": body,
                    "path": str(f)
                }
                
                print(f"[SKILL] Loaded: {name} ({f.parent.name})")
            
            except Exception as e:
                print(f"[ERROR] Failed to load {f}: {e}")
    
    def _parse_frontmatter(self, text: str) -> Tuple[Dict, str]:
        """
        解析 YAML frontmatter
        
        格式：
        ---
        name: pdf
        description: Process PDF files
        tags: document
        ---
        (正文内容)
        
        Args:
            text: 文件内容
        
        Returns:
            Tuple[Dict, str]: (元数据字典, 正文内容)
        
        Example:
            >>> meta, body = loader._parse_frontmatter(text)
            >>> meta
            {'name': 'pdf', 'description': 'Process PDF files'}
            >>> body
            '# PDF Processing\n\n...'
        """
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as e:
            print(f"[WARN] Failed to parse YAML frontmatter: {e}")
            meta = {}
        
        return meta, match.group(2).strip()
    
    def get_descriptions(self) -> str:
        """
        Layer 1：返回所有技能的简短描述
        
        用于注入系统提示词，让模型知道有哪些技能可用。
        
        Returns:
            str: 技能描述列表（多行文本）
        
        Example:
            >>> loader.get_descriptions()
            '  - pdf: Process PDF files [document]\n  - code-review: Review code quality [development]'
        """
        if not self.skills:
            return "(no skills available)"
        
        lines = []
        for name, skill in self.skills.items():
            desc = skill["meta"].get("description", "No description")
            tags = skill["meta"].get("tags", "")
            
            line = f"  - {name}: {desc}"
            if tags:
                line += f" [{tags}]"
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def get_content(self, name: str) -> str:
        """
        Layer 2：返回指定技能的完整内容
        
        包装在 <skill> 标签中，方便模型识别。
        
        Args:
            name: 技能名称
        
        Returns:
            str: 完整的技能内容（包含 <skill> 标签）
        
        Example:
            >>> content = loader.get_content("pdf")
            >>> print(content)
            <skill name="pdf">
            # PDF Processing Guide
            ...
            </skill>
        """
        skill = self.skills.get(name)
        if not skill:
            available = ', '.join(self.skills.keys())
            return f"Error: Unknown skill '{name}'. Available: {available}"
        
        return f"<skill name=\"{name}\">\n{skill['body']}\n</skill>"
    
    def list_skills(self) -> list:
        """
        获取所有技能名称列表
        
        Returns:
            list: 技能名称列表
        
        Example:
            >>> loader.list_skills()
            ['pdf', 'code-review', 'mcp-builder']
        """
        return list(self.skills.keys())
