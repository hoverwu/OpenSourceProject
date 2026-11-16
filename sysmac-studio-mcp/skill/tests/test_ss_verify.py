"""Unit tests for ss_verify against synthetic .smc2 archives (stdlib only)."""
import os
import tempfile
import unittest
import zipfile

import _stubs

import ss_verify as V

OEM = '''<?xml version="1.0" encoding="utf-8"?>
<sysmac schemaVersion="1">
 <Entity type="Solution" id="s0" name="Proj">
  <ChildEntities>
   <Entity type="Program" subtype="MultipartLadder" id="p1" name="PrgDemo">
    <ChildEntities>
     <Entity type="Variables" subtype="Ladder" id="v1" name="Vars"/>
     <Entity type="PouBody" subtype="Ladder" id="b1" name="PrgMain"/>
    </ChildEntities>
   </Entity>
   <Entity type="NexTask" id="t1" name="Task0">
    <ChildEntities/>
   </Entity>
  </ChildEntities>
 </Entity>
</sysmac>
'''

TASK_XML = ('<data><TaskExecutionCondition>200000</TaskExecutionCondition>'
            '<AssociatedProgramData ProgramName="%s" SequenceNumber="1"/></data>')

# 安全 CPU 实体在原件里本就没有同 id 的 .xml（实测两工程一致）；名字/ID 都是
# 合成的，只为覆盖"未验证格式不得按普通程序规则判缺文件"。
SAFETY_OEM = '''<?xml version="1.0" encoding="utf-8"?>
<sysmac schemaVersion="1">
 <Entity type="Solution" id="s0" name="Proj">
  <ChildEntities>
   <Entity type="Program" subtype="SafetyExtendedProgram" id="sp1" name="SPrg">
    <ChildEntities>
     <Entity type="Variables" subtype="SafetyExtendedProgramLocal" id="sv1" name="SVars"/>
     <Entity type="PouBody" subtype="FBDExtended" id="sb1" name="SBody"/>
     <Entity type="Variables" subtype="SafetyGlobal" id="sg1" name="SGlobal"/>
    </ChildEntities>
   </Entity>
   <Entity type="NexTask" id="t1" name="Task0">
    <ChildEntities/>
   </Entity>
  </ChildEntities>
 </Entity>
</sysmac>
'''


def build_archive(path, program_name='PrgDemo', assoc='PrgDemo',
                  with_vars=True, task_child=None, oem=OEM,
                  vars_dir='sol', vars_ext='.xml', extra=()):
    folder = 'sol'
    if task_child:
        oem = oem.replace('<Entity type="NexTask" id="t1" name="Task0">\n    <ChildEntities/>',
                          '<Entity type="NexTask" id="t1" name="Task0">\n    <ChildEntities>'
                          + task_child + '</ChildEntities>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(folder + '/' + folder + '.oem', b'\xef\xbb\xbf' + oem.encode('utf-8'))
        if with_vars:
            z.writestr(vars_dir + '/v1' + vars_ext, b'<data/>')
        z.writestr(folder + '/b1.xml', b'{}')
        z.writestr(folder + '/t1.xml', (TASK_XML % assoc).encode('utf-8'))
        for name, data in extra:
            z.writestr(name, data)


class Verify(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'proj.smc2')

    def tearDown(self):
        self.dir.cleanup()

    def test_valid_passes(self):
        build_archive(self.path)
        lines, fails = V.verify(self.path, program='PrgDemo')
        self.assertEqual(fails, [])
        self.assertTrue(any('RESULT' not in ln and ln.startswith('[PASS]') for ln in lines))

    def test_missing_program_fails(self):
        build_archive(self.path)
        _, fails = V.verify(self.path, program='Ghost')
        self.assertTrue(any('not found' in f for f in fails))

    def test_dangling_association_fails(self):
        build_archive(self.path, assoc='Ghost')
        _, fails = V.verify(self.path)
        self.assertTrue(any('dangling' in f for f in fails))

    def test_missing_companion_fails(self):
        build_archive(self.path, with_vars=False)
        _, fails = V.verify(self.path)
        self.assertTrue(any('companions' in f for f in fails))

    def test_corrupt_zip_fails(self):
        with open(self.path, 'wb') as fh:
            fh.write(b'this is not a zip')
        _, fails = V.verify(self.path)
        self.assertTrue(fails)

    def test_missing_file_fails(self):
        _, fails = V.verify(os.path.join(self.dir.name, 'absent.smc2'))
        self.assertTrue(fails)

    def test_assoc_without_entity_is_info_not_fail(self):
        build_archive(self.path)
        lines, fails = V.verify(self.path)
        self.assertEqual(fails, [])
        self.assertTrue(any(ln.startswith('[INFO]') and 'UNVERIFIED' in ln for ln in lines))

    def test_assoc_entity_present_no_warning(self):
        build_archive(self.path, task_child='<Entity type="NexAssociatedProgram" id="a1"/>')
        lines, fails = V.verify(self.path)
        self.assertEqual(fails, [])
        self.assertFalse(any('UNVERIFIED' in ln for ln in lines))

    def test_non_sysmac_root_fails(self):
        build_archive(self.path, oem='<?xml version="1.0"?><foo/>')
        _, fails = V.verify(self.path)
        self.assertTrue(any('not <sysmac>' in f for f in fails))

    def test_empty_entity_tree_fails(self):
        build_archive(self.path, oem='<?xml version="1.0"?><sysmac schemaVersion="1"/>')
        _, fails = V.verify(self.path)
        self.assertTrue(any('no Entity' in f for f in fails))

    def test_duplicate_entity_id_fails(self):
        dup = OEM.replace('id="b1"', 'id="v1"')   # b1 改成与 v1 同 id
        build_archive(self.path, oem=dup)
        _, fails = V.verify(self.path)
        self.assertTrue(any('duplicate entity id' in f for f in fails))

    def test_library_folder_companion_does_not_mask(self):
        # v1.xml 只在库目录里，主工程根目录缺 → 仍判缺文件。
        build_archive(self.path, with_vars=False, extra=[('sol/lib/v1.xml', b'<data/>')])
        _, fails = V.verify(self.path)
        self.assertTrue(any('companions' in f for f in fails))

    def test_wrong_extension_does_not_mask(self):
        # 只有 v1.txt（非 .xml）不能顶替配套 xml。
        build_archive(self.path, with_vars=False, extra=[('sol/v1.txt', b'<data/>')])
        _, fails = V.verify(self.path)
        self.assertTrue(any('companions' in f for f in fails))

    def test_sourceholder_child_exempt(self):
        # SourceHolder 子实体允许无配套文件，--program 不应判它缺文件。
        oem = OEM.replace('<Entity type="PouBody" subtype="Ladder" id="b1" name="PrgMain"/>',
                          '<Entity type="PouBody" subtype="Ladder" id="b1" name="PrgMain"/>'
                          '<Entity type="SourceHolder" id="sh1" name="Src"/>')
        build_archive(self.path, oem=oem)
        _, fails = V.verify(self.path, program='PrgDemo')
        self.assertEqual(fails, [])

    def test_nonexempt_child_still_checked(self):
        # 豁免只针对 SourceHolder；PouBody 缺配套仍需 FAIL。
        oem = OEM.replace('<Entity type="PouBody" subtype="Ladder" id="b1" name="PrgMain"/>',
                          '<Entity type="PouBody" subtype="Ladder" id="b2" name="PrgMain"/>')
        build_archive(self.path, oem=oem)   # 归档里只有 b1.xml，没有 b2.xml
        _, fails = V.verify(self.path, program='PrgDemo')
        self.assertTrue(any('program child' in f for f in fails))

    def test_safety_formats_reported_not_failed(self):
        # 安全 CPU 实体没有同 id .xml 是原件的正常形态：不判 FAIL，只记 INFO。
        build_archive(self.path, oem=SAFETY_OEM, assoc='SPrg')
        lines, fails = V.verify(self.path, program='SPrg')
        self.assertEqual(fails, [])
        self.assertTrue(any(ln.startswith('[INFO]') and 'unverified safety' in ln
                            and 'NOT a pass' in ln for ln in lines))

    def test_safety_scope_does_not_mask_normal_missing(self):
        # 同一归档里普通格式仍严格判缺文件，未被安全豁免顺带放过。
        oem = SAFETY_OEM.replace(
            '<Entity type="Variables" subtype="SafetyGlobal" id="sg1" name="SGlobal"/>',
            '<Entity type="Variables" subtype="Ladder" id="sg1" name="SGlobal"/>')
        build_archive(self.path, oem=oem, assoc='SPrg')
        _, fails = V.verify(self.path)
        self.assertTrue(any('companions' in f for f in fails))

    def test_ambiguous_program_fails(self):
        oem = OEM.replace('id="p1" name="PrgDemo"', 'id="p1" name="PrgDemo"')
        oem = oem.replace('</ChildEntities>\n   </Entity>\n   <Entity type="NexTask"',
                          '<Entity type="Program" subtype="MultipartLadder" id="p2" name="PrgDemo"/>'
                          '</ChildEntities>\n   </Entity>\n   <Entity type="NexTask"')
        build_archive(self.path, oem=oem)
        _, fails = V.verify(self.path, program='PrgDemo')
        self.assertTrue(any('ambiguous' in f for f in fails))

    def test_testzip_exception_fails(self):
        build_archive(self.path)
        orig = zipfile.ZipFile.testzip

        def boom(self):
            raise RuntimeError('crc boom')

        zipfile.ZipFile.testzip = boom
        try:
            lines, fails = V.verify(self.path)
        finally:
            zipfile.ZipFile.testzip = orig
        self.assertTrue(any('testzip raised' in f for f in fails))
        self.assertTrue(any(ln.startswith('[FAIL]') for ln in lines))


class MainExit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'proj.smc2')

    def tearDown(self):
        self.dir.cleanup()

    def test_pass_exit_zero(self):
        build_archive(self.path)
        self.assertEqual(V.main([self.path, '--program', 'PrgDemo']), 0)

    def test_fail_exit_nonzero(self):
        build_archive(self.path, assoc='Ghost')
        self.assertEqual(V.main([self.path]), 1)

    def test_report_written(self):
        build_archive(self.path)
        rep = os.path.join(self.dir.name, 'rep.txt')
        V.main([self.path, '--report', rep])
        with open(rep, encoding='utf-8') as fh:
            self.assertIn('RESULT = PASS', fh.read())


if __name__ == '__main__':
    unittest.main()